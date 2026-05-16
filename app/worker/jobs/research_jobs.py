from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.clients.kalshi import KalshiClient, dollars_to_cents, quantity_to_int
from app.clients.optic_odds import OpticOddsClient
from app.config import settings
from app.db import SessionLocal
from app.models import (
    DerivedMarketMetric,
    KalshiPrivateFill,
    KalshiPrivateOrder,
    KalshiOrderbookSnapshot,
    KalshiTrade,
    Market,
    MarketEventDetection,
    MarketFeatureBucket,
    LiveMarketSignal,
    OpportunityScore,
    SharpBookLimitsSnapshot,
    SharpBookOddsSnapshot,
)
from app.repositories import JobRunRepository, MarketRepository, SnapshotRepository, utcnow
from app.services.devig import american_to_decimal, american_to_probability, multiplicative_devig
from app.services.event_detection import detect_recent_market_events
from app.services.feature_buckets import build_recent_feature_buckets
from app.services.live_signals import build_live_signals
from app.services.metrics import build_metric, calculate_spread, contracts_per_minute
from app.services.scoring import build_opportunity_score

logger = logging.getLogger(__name__)

KALSHI_SERIES_PREFIX_BY_LEAGUE = {
    "mlb": ["KXMLBGAME"],
    "nba": ["KXNBAGAME"],
    "nfl": ["KXNFLGAME"],
    "nhl": ["KXNHLGAME"],
    "ncaab": ["KXNCAAMBGAME"],
    "ufc": ["KXUFCFIGHT"],
    "atp": ["KXATPMATCH"],
    "wta": ["KXWTAMATCH"],
    "epl": ["KXEPLGAME"],
    "ucl": ["KXUCLGAME"],
}

OPTIC_DISCOVERY_MARKETS_BY_LEAGUE = {
    "mlb": ["Moneyline", "Run Line", "Total Runs", "1st Half Total Runs"],
}

OPTIC_MARKET_BY_KALSHI_SERIES = {
    "KXMLBGAME": "Moneyline",
    "KXMLBSPREAD": "Run Line",
    "KXMLBTOTAL": "Total Runs",
    "KXMLBF5TOTAL": "1st Half Total Runs",
}

MLB_TEAM_SELECTION_HINTS = {
    "ARI": ["arizona", "diamondbacks"],
    "AZ": ["arizona", "diamondbacks"],
    "ATH": ["athletics", "a's"],
    "ATL": ["atlanta", "braves"],
    "BAL": ["baltimore", "orioles"],
    "BOS": ["boston", "red sox"],
    "CHC": ["chicago cubs", "cubs"],
    "CIN": ["cincinnati", "reds"],
    "CLE": ["cleveland", "guardians"],
    "COL": ["colorado", "rockies"],
    "CWS": ["chicago white sox", "white sox"],
    "DET": ["detroit", "tigers"],
    "HOU": ["houston", "astros"],
    "KC": ["kansas city", "royals"],
    "LAA": ["los angeles angels", "angels"],
    "LAD": ["los angeles dodgers", "dodgers"],
    "MIA": ["miami", "marlins"],
    "MIL": ["milwaukee", "brewers"],
    "MIN": ["minnesota", "twins"],
    "NYM": ["new york mets", "mets"],
    "NYY": ["new york yankees", "yankees"],
    "PHI": ["philadelphia", "phillies"],
    "PIT": ["pittsburgh", "pirates"],
    "SD": ["san diego", "padres"],
    "SEA": ["seattle", "mariners"],
    "SF": ["san francisco", "giants"],
    "STL": ["st. louis", "st louis", "cardinals"],
    "TB": ["tampa bay", "rays"],
    "TEX": ["texas", "rangers"],
    "TOR": ["toronto", "blue jays"],
    "WSH": ["washington", "nationals"],
}


def run_tracked_job(job_name: str, func: Callable[[Session], int]) -> None:
    db = SessionLocal()
    repo = JobRunRepository(db)
    run = repo.start(job_name)
    try:
        rows = func(db)
    except Exception as exc:
        logger.exception("Job failed: %s", job_name)
        repo.finish(run, "failed", error_message=str(exc))
    else:
        repo.finish(run, "success", rows_inserted=rows)
    finally:
        db.close()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def discover_markets_job() -> None:
    run_tracked_job("discover_markets", lambda db: asyncio.run(discover_markets(db)))


async def discover_markets(db: Session) -> int:
    repo = MarketRepository(db)
    rows = 0
    seen_tickers: set[str] = set()
    optic = OpticOddsClient(settings.optic_odds_base_url, settings.oddsjam_api_key)
    now = utcnow()
    start_after = now.isoformat().replace("+00:00", "Z")
    start_before = (now + timedelta(days=2)).isoformat().replace("+00:00", "Z")

    for league in settings.polling_leagues:
        try:
            fixture_payload = await optic.fixtures(
                league=league,
                start_date_after=start_after,
                start_date_before=start_before,
                limit=100,
            )
        except Exception:
            logger.exception("Optic fixture discovery failed for league=%s", league)
            continue

        fixtures = fixture_payload.get("data", fixture_payload if isinstance(fixture_payload, list) else [])
        mapping_payloads = await fetch_optic_kalshi_mappings(optic, fixtures, discovery_market_names(league))
        for fixture, market_name, odds_payload in mapping_payloads:
            fixture_id = str(fixture.get("id"))
            for odds in _iter_odds(odds_payload):
                ticker = odds.get("source_ids", {}).get("market_id")
                if not ticker or ticker in seen_tickers:
                    continue
                seen_tickers.add(ticker)
                repo.upsert_market(
                    ticker=ticker,
                    sport=(fixture.get("sport") or {}).get("id"),
                    league=league,
                    market_type=market_name,
                    event_title=f"{fixture.get('away_team_display')} @ {fixture.get('home_team_display')}",
                    event_start_time=parse_dt(fixture.get("start_date")),
                    status=fixture.get("status"),
                    optic_fixture_id=fixture_id,
                    raw_payload={"fixture": fixture, "optic_kalshi_odds": odds},
                )
                rows += 1
            db.commit()

    kalshi = KalshiClient(settings.kalshi_base_url, settings.kalshi_api_key, settings.kalshi_private_key)
    configured_prefixes = settings.kalshi_series_prefixes
    for league in settings.polling_leagues:
        prefixes = discovery_series_prefixes(league, configured_prefixes)
        for prefix in prefixes:
            cursor: str | None = None
            for _ in range(5):
                try:
                    payload = await kalshi.list_markets(prefix, cursor=cursor)
                except Exception:
                    logger.exception("Kalshi series discovery failed for prefix=%s", prefix)
                    break
                for market in payload.get("markets", []):
                    ticker = market["ticker"]
                    if ticker in seen_tickers:
                        continue
                    seen_tickers.add(ticker)
                    fixture_metadata = infer_fixture_metadata(db, ticker)
                    repo.upsert_market(
                        ticker=ticker,
                        sport=fixture_metadata.get("sport"),
                        league=league,
                        market_type=prefix,
                        event_title=market.get("subtitle") or market.get("title"),
                        event_start_time=fixture_metadata.get("event_start_time"),
                        status=market.get("status"),
                        optic_fixture_id=fixture_metadata.get("optic_fixture_id"),
                        raw_payload=market,
                    )
                    rows += 1
                cursor = payload.get("cursor")
                if not cursor:
                    break
            db.commit()

    db.commit()
    return rows


def discovery_series_prefixes(league: str, configured_prefixes: list[str]) -> list[str]:
    defaults = KALSHI_SERIES_PREFIX_BY_LEAGUE.get(league, [])
    allowed = set(defaults)
    configured = [prefix for prefix in configured_prefixes if prefix in allowed]
    return list(dict.fromkeys([*configured, *defaults]))


def discovery_market_names(league: str) -> list[str]:
    market_names = [*settings.polling_markets]
    market_names.extend(OPTIC_DISCOVERY_MARKETS_BY_LEAGUE.get(league, []))
    return list(dict.fromkeys(market_names))


def infer_fixture_metadata(db: Session, ticker: str) -> dict[str, Any]:
    event_code = kalshi_event_code(ticker)
    if not event_code:
        return {}
    mapped_market = db.scalar(
        select(Market)
        .where(
            Market.ticker.like(f"KXMLBGAME-{event_code}-%"),
            Market.optic_fixture_id.isnot(None),
        )
        .limit(1)
    )
    if mapped_market is None:
        return {}
    return {
        "sport": mapped_market.sport,
        "optic_fixture_id": mapped_market.optic_fixture_id,
        "event_start_time": mapped_market.event_start_time,
    }


def kalshi_event_code(ticker: str) -> str | None:
    parts = ticker.split("-")
    return parts[1] if len(parts) >= 3 else None


def should_poll_sharp_market(market: Market) -> bool:
    if market.market_type in {"Moneyline", "Run Line", "Total Runs", "1st Half Total Runs", "KXMLBGAME"}:
        return True
    raw_payload = market.raw_payload or {}
    return "optic_kalshi_odds" in raw_payload


async def fetch_optic_kalshi_mappings(
    optic: OpticOddsClient,
    fixtures: list[dict[str, Any]],
    market_names: list[str],
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    semaphore = asyncio.Semaphore(max(1, settings.optic_discovery_concurrency))

    async def fetch_one(fixture: dict[str, Any], market_name: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        fixture_id = str(fixture.get("id"))
        try:
            async with semaphore:
                payload = await optic.fixture_odds(
                    fixture_id=fixture_id,
                    sportsbooks=["Kalshi"],
                    market=market_name,
                    is_main=True,
                )
        except Exception:
            logger.exception("Optic Kalshi mapping failed for fixture=%s market=%s", fixture_id, market_name)
            return fixture, market_name, None
        return fixture, market_name, payload

    tasks = [fetch_one(fixture, market_name) for fixture in fixtures for market_name in market_names]
    results = await asyncio.gather(*tasks)
    return [(fixture, market_name, payload) for fixture, market_name, payload in results if payload is not None]


def pull_kalshi_orderbooks_job() -> None:
    run_tracked_job("pull_kalshi_orderbooks", lambda db: asyncio.run(pull_kalshi_orderbooks(db)))


async def pull_kalshi_orderbooks(db: Session) -> int:
    client = KalshiClient(settings.kalshi_base_url, settings.kalshi_api_key, settings.kalshi_private_key)
    rows = 0
    markets = MarketRepository(db).active_for_polling()
    now = utcnow()
    snapshots = SnapshotRepository(db)
    for market in markets:
        try:
            orderbook = await client.get_orderbook(market.ticker)
            market_payload = await client.get_market(market.ticker)
        except Exception:
            logger.exception("Kalshi orderbook poll failed for ticker=%s", market.ticker)
            continue

        market_data = market_payload.get("market", {})
        volume = market_volume(market_data)
        recent = snapshots.orderbooks_since(market.id, now - timedelta(minutes=10))
        cpm = contracts_per_minute(recent) if recent else None
        best_yes_ask_qty = orderbook.no.get(orderbook.best_no_bid or -1, 0)
        best_no_ask_qty = orderbook.yes.get(orderbook.best_yes_bid or -1, 0)
        snapshot = KalshiOrderbookSnapshot(
            market_id=market.id,
            timestamp=now,
            best_yes_bid=orderbook.best_yes_bid,
            best_yes_ask=orderbook.best_yes_ask,
            best_no_bid=orderbook.best_no_bid,
            best_no_ask=orderbook.best_no_ask,
            yes_bid_depth=sum(orderbook.yes.values()),
            yes_ask_depth=best_yes_ask_qty,
            no_bid_depth=sum(orderbook.no.values()),
            no_ask_depth=best_no_ask_qty,
            total_depth=sum(orderbook.yes.values()) + sum(orderbook.no.values()),
            spread=calculate_spread(orderbook.best_yes_bid, orderbook.best_yes_ask),
            contracts_per_minute=cpm,
            volume=volume,
            yes_book={str(price): qty for price, qty in orderbook.yes.items()},
            no_book={str(price): qty for price, qty in orderbook.no.items()},
        )
        db.add(snapshot)
        market.status = market_data.get("status") or market.status
        market.event_title = market_data.get("title") or market_data.get("subtitle") or market.event_title
        rows += 1
    db.commit()
    return rows


def pull_kalshi_trades_job() -> None:
    run_tracked_job("pull_kalshi_trades", lambda db: asyncio.run(pull_kalshi_trades(db)))


async def pull_kalshi_trades(db: Session) -> int:
    client = KalshiClient(settings.kalshi_base_url, settings.kalshi_api_key, settings.kalshi_private_key)
    rows = 0
    for market in MarketRepository(db).active_for_polling():
        try:
            payload = await client.get_trades(market.ticker, limit=100)
        except Exception:
            logger.exception("Kalshi trades poll failed for ticker=%s", market.ticker)
            continue
        rows += insert_trade_rows(db, market, payload.get("trades", []))
    db.commit()
    return rows


def fast_poll_live_markets_job() -> None:
    run_tracked_job("fast_poll_live_markets", lambda db: asyncio.run(fast_poll_live_markets(db)))


async def fast_poll_live_markets(db: Session) -> int:
    if not settings.fast_poll_enabled:
        return 0
    client = KalshiClient(settings.kalshi_base_url, settings.kalshi_api_key, settings.kalshi_private_key)
    rows = 0
    markets = MarketRepository(db).fast_poll_candidates(
        limit=settings.fast_poll_market_limit,
        window_minutes=settings.fast_poll_window_minutes,
    )
    for market in markets:
        now = utcnow()
        try:
            orderbook = await client.get_orderbook(market.ticker)
            market_payload = await client.get_market(market.ticker)
            trades_payload = await client.get_trades(market.ticker, limit=100)
        except Exception:
            logger.exception("Fast poll failed for ticker=%s", market.ticker)
            continue

        market_data = market_payload.get("market", {})
        volume = market_volume(market_data)
        recent = SnapshotRepository(db).orderbooks_since(market.id, now - timedelta(minutes=10))
        cpm = contracts_per_minute(recent) if recent else None
        db.add(
            KalshiOrderbookSnapshot(
                market_id=market.id,
                timestamp=now,
                best_yes_bid=orderbook.best_yes_bid,
                best_yes_ask=orderbook.best_yes_ask,
                best_no_bid=orderbook.best_no_bid,
                best_no_ask=orderbook.best_no_ask,
                yes_bid_depth=sum(orderbook.yes.values()),
                yes_ask_depth=orderbook.no.get(orderbook.best_no_bid or -1, 0),
                no_bid_depth=sum(orderbook.no.values()),
                no_ask_depth=orderbook.yes.get(orderbook.best_yes_bid or -1, 0),
                total_depth=sum(orderbook.yes.values()) + sum(orderbook.no.values()),
                spread=calculate_spread(orderbook.best_yes_bid, orderbook.best_yes_ask),
                contracts_per_minute=cpm,
                volume=volume,
                yes_book={str(price): qty for price, qty in orderbook.yes.items()},
                no_book={str(price): qty for price, qty in orderbook.no.items()},
            )
        )
        rows += 1
        market.status = market_data.get("status") or market.status
        market.event_title = market_data.get("title") or market_data.get("subtitle") or market.event_title
        rows += insert_trade_rows(db, market, trades_payload.get("trades", []))
        rows += build_live_signals(db, market, now=now)
    db.commit()
    return rows


def pull_kalshi_private_fills_job() -> None:
    run_tracked_job("pull_kalshi_private_fills", lambda db: asyncio.run(pull_kalshi_private_fills(db)))


async def pull_kalshi_private_fills(db: Session) -> int:
    if not settings.kalshi_private_data_enabled:
        return 0
    client = KalshiClient(settings.kalshi_base_url, settings.kalshi_api_key, settings.kalshi_private_key)
    rows = 0
    rows += await pull_private_orders(db, client)
    rows += await pull_private_fills(db, client)
    db.commit()
    return rows


async def pull_private_orders(db: Session, client: KalshiClient) -> int:
    rows = 0
    try:
        payload = await client.get_portfolio_orders(limit=100)
    except Exception:
        logger.exception("Kalshi private orders poll failed")
        return 0
    for order in payload.get("orders", []):
        order_id = str(order.get("order_id") or order.get("id") or "")
        ticker = order.get("ticker")
        market = MarketRepository(db).by_ticker(ticker) if ticker else None
        if not order_id or market is None or db.scalar(select(KalshiPrivateOrder).where(KalshiPrivateOrder.order_id == order_id)):
            continue
        created_at = parse_dt(order.get("created_time") or order.get("created_at"))
        if created_at is None:
            continue
        db.add(
            KalshiPrivateOrder(
                order_id=order_id,
                market_id=market.id,
                created_at=created_at,
                side=order.get("side") or order.get("outcome"),
                action=order.get("action"),
                price=order_price(order),
                quantity=float(order.get("count") or order.get("count_fp") or order.get("quantity") or 0),
                status=order.get("status"),
                raw_payload=order,
            )
        )
        rows += 1
    return rows


async def pull_private_fills(db: Session, client: KalshiClient) -> int:
    rows = 0
    try:
        payload = await client.get_portfolio_fills(limit=100)
    except Exception:
        logger.exception("Kalshi private fills poll failed")
        return 0
    for fill in payload.get("fills", []):
        fill_id = str(fill.get("fill_id") or fill.get("trade_id") or fill.get("id") or "")
        ticker = fill.get("ticker")
        market = MarketRepository(db).by_ticker(ticker) if ticker else None
        if not fill_id or market is None or db.scalar(select(KalshiPrivateFill).where(KalshiPrivateFill.fill_id == fill_id)):
            continue
        timestamp = parse_dt(fill.get("created_time") or fill.get("created_at"))
        if timestamp is None:
            continue
        db.add(
            KalshiPrivateFill(
                fill_id=fill_id,
                order_id=fill.get("order_id"),
                market_id=market.id,
                timestamp=timestamp,
                side=fill.get("side") or fill.get("outcome"),
                price=order_price(fill),
                quantity=float(fill.get("count") or fill.get("count_fp") or fill.get("quantity") or 0),
                fee=float(fill.get("fee") or fill.get("fee_dollars") or 0),
                raw_payload=fill,
            )
        )
        rows += 1
    return rows


def pull_sharp_book_odds_job() -> None:
    run_tracked_job("pull_sharp_book_odds", lambda db: asyncio.run(pull_sharp_book_odds(db, include_limits=False)))


def pull_sharp_book_limits_job() -> None:
    run_tracked_job("pull_sharp_book_limits", lambda db: asyncio.run(pull_sharp_book_odds(db, include_limits=True)))


async def pull_sharp_book_odds(db: Session, include_limits: bool) -> int:
    client = OpticOddsClient(settings.optic_odds_base_url, settings.oddsjam_api_key)
    rows = 0
    now = utcnow()
    markets = [
        market
        for market in MarketRepository(db).active_for_polling()
        if market.optic_fixture_id and should_poll_sharp_market(market)
    ]
    for market in markets:
        try:
            payload = await client.fixture_odds(
                fixture_id=market.optic_fixture_id or "",
                sportsbooks=settings.sharp_books,
                market=optic_market_name(market.market_type),
                is_main=True,
            )
        except Exception:
            logger.exception("Optic odds poll failed for ticker=%s", market.ticker)
            continue

        target_team = target_team_from_market(market)
        grouped: dict[str, dict[str, float]] = {}
        staged: list[dict[str, Any]] = []
        for odds in _iter_odds(payload):
            price = odds.get("price")
            if price is None:
                continue
            side = _normalize_side(odds, target_team=target_team)
            implied = american_to_probability(int(price))
            selection_key = str(odds.get("selection") or odds.get("name") or side)
            grouped.setdefault(odds["sportsbook"], {})[selection_key] = implied
            staged.append({"odds": odds, "side": side, "implied": implied})

        devig_by_book_selection: dict[tuple[str, str], float] = {}
        for sportsbook, probs in grouped.items():
            for selection, probability in multiplicative_devig(probs).items():
                devig_by_book_selection[(sportsbook, selection)] = probability

        for item in staged:
            odds = item["odds"]
            side = item["side"]
            selection_key = str(odds.get("selection") or odds.get("name") or side)
            db.add(
                SharpBookOddsSnapshot(
                    market_id=market.id,
                    timestamp=now,
                    sportsbook=odds["sportsbook"],
                    side=side,
                    american_odds=int(odds["price"]),
                    decimal_odds=american_to_decimal(int(odds["price"])),
                    implied_probability=item["implied"],
                    devigged_probability=devig_by_book_selection.get((odds["sportsbook"], selection_key)),
                    raw_payload=odds,
                )
            )
            rows += 1
            limit_amount = (odds.get("limits") or {}).get("max")
            if include_limits and limit_amount is not None:
                db.add(
                    SharpBookLimitsSnapshot(
                        market_id=market.id,
                        timestamp=now,
                        sportsbook=odds["sportsbook"],
                        side=side,
                        limit_amount=float(limit_amount),
                    )
                )
                rows += 1
    db.commit()
    return rows


def calculate_derived_metrics_job() -> None:
    run_tracked_job("calculate_derived_metrics", calculate_derived_metrics)


def calculate_derived_metrics(db: Session) -> int:
    rows = 0
    snapshots = SnapshotRepository(db)
    for market in MarketRepository(db).active_for_polling():
        latest_orderbook = snapshots.latest_orderbook(market.id)
        if latest_orderbook is None:
            continue
        recent_orderbooks = snapshots.orderbooks_since(market.id, utcnow() - timedelta(minutes=10))
        recent_sharp_odds = snapshots.latest_sharp_odds(market.id, window_minutes=10)
        db.add(build_metric(market, latest_orderbook, recent_orderbooks, recent_sharp_odds))
        rows += 1
    db.commit()
    return rows


def calculate_opportunity_scores_job() -> None:
    run_tracked_job("calculate_opportunity_scores", calculate_opportunity_scores)


def calculate_opportunity_scores(db: Session) -> int:
    rows = 0
    snapshots = SnapshotRepository(db)
    for market in MarketRepository(db).active_for_polling():
        latest_orderbook = snapshots.latest_orderbook(market.id)
        latest_metric = snapshots.latest_metric(market.id)
        if latest_orderbook is None or latest_metric is None:
            continue
        limits = snapshots.latest_limits(market.id)
        db.add(build_opportunity_score(latest_metric, latest_orderbook, limits))
        rows += 1
    db.commit()
    return rows


def calculate_market_feature_buckets_job() -> None:
    run_tracked_job("calculate_market_feature_buckets", calculate_market_feature_buckets)


def calculate_market_feature_buckets(db: Session) -> int:
    return build_recent_feature_buckets(
        db,
        MarketRepository(db).active_for_polling(),
        lookback_minutes=settings.feature_bucket_lookback_minutes,
    )


def detect_market_events_job() -> None:
    run_tracked_job("detect_market_events", detect_market_events)


def detect_market_events(db: Session) -> int:
    return detect_recent_market_events(db, MarketRepository(db).active_for_polling())


def cleanup_aggregation_job() -> None:
    run_tracked_job("cleanup_aggregation", cleanup_aggregation)


def cleanup_aggregation(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = 0
    for model in (KalshiOrderbookSnapshot, SharpBookOddsSnapshot, SharpBookLimitsSnapshot):
        result = db.execute(delete(model).where(model.timestamp < cutoff))
        rows += result.rowcount or 0
    db.commit()
    return rows


def _iter_odds(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fixture in payload.get("data", []):
        rows.extend(fixture.get("odds", []))
    return rows


def market_volume(market_data: dict[str, Any]) -> int | None:
    for key in ("volume", "volume_fp", "volume_24h", "volume_24h_fp"):
        value = market_data.get(key)
        if value is not None:
            return quantity_to_int(value)
    return None


def insert_trade_rows(db: Session, market: Market, trades: list[dict[str, Any]]) -> int:
    rows = 0
    for trade in trades:
        trade_id = str(trade.get("trade_id") or "")
        if not trade_id or db.scalar(select(KalshiTrade).where(KalshiTrade.trade_id == trade_id)):
            continue
        timestamp = parse_dt(trade.get("created_time"))
        if timestamp is None:
            continue
        db.add(
            KalshiTrade(
                market_id=market.id,
                trade_id=trade_id,
                timestamp=timestamp,
                count=float(trade.get("count_fp") or trade.get("count") or 0),
                yes_price=dollars_to_cents(trade.get("yes_price_dollars")),
                no_price=dollars_to_cents(trade.get("no_price_dollars")),
                taker_side=trade.get("taker_side") or trade.get("taker_outcome_side"),
                taker_book_side=trade.get("taker_book_side"),
                raw_payload=trade,
            )
        )
        rows += 1
    return rows


def order_price(payload: dict[str, Any]) -> int | None:
    for key in ("price", "yes_price", "no_price"):
        value = payload.get(key)
        if value is not None:
            numeric = float(value)
            return dollars_to_cents(numeric) if 0 < numeric <= 1 else int(numeric)
    for key in ("price_dollars", "yes_price_dollars", "no_price_dollars"):
        value = payload.get(key)
        if value is not None:
            return dollars_to_cents(value)
    return None


def _normalize_side(odds: dict[str, Any], target_team: str | None = None) -> str:
    selection_line = odds.get("selection_line")
    if selection_line:
        return str(selection_line).lower()
    selection = str(odds.get("selection") or odds.get("name") or "selection").lower()
    if selection in {"draw", "tie", "x", "the draw"}:
        return "draw"
    if target_team and selection_matches_team(selection, target_team):
        return "yes"
    if target_team:
        return "no"
    # TODO: Map exact Optic selections to Kalshi YES/NO semantics per market type.
    return "selection"


def optic_market_name(market_type: str | None) -> str:
    if not market_type:
        return "Moneyline"
    return OPTIC_MARKET_BY_KALSHI_SERIES.get(market_type, market_type)


def target_team_from_market(market: Market) -> str | None:
    if market.market_type not in {"Moneyline", "KXMLBGAME"}:
        return None
    suffix = market.ticker.rsplit("-", 1)[-1]
    hints = MLB_TEAM_SELECTION_HINTS.get(suffix)
    if hints:
        return "|".join(hints)
    raw_yes = (market.raw_payload or {}).get("yes_sub_title")
    return str(raw_yes) if raw_yes else suffix


def selection_matches_team(selection: str, target_team: str) -> bool:
    normalized_selection = selection.lower()
    return any(hint and hint.lower() in normalized_selection for hint in target_team.split("|"))
