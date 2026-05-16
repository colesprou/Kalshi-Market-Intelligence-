from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import KalshiOrderbookSnapshot, KalshiTrade, LiveMarketSignal, Market

LIVE_FLOW_SPIKE_MIN_CONTRACTS_10S = 20.0
LIVE_FLOW_SPIKE_MIN_RATIO = 3.0
ONE_SIDED_MIN_CONTRACTS_10S = 10.0
ONE_SIDED_MIN_IMBALANCE = 0.75
PRICE_DRIFT_MIN_CENTS = 2
STALE_MAX_PRICE_CHANGE_CENTS = 0
STALE_MAX_SPREAD_CHANGE_CENTS = 0


def build_live_signals(db: Session, market: Market, now: datetime | None = None) -> int:
    timestamp = now or datetime.now(timezone.utc)
    latest_orderbook = latest_orderbook_before(db, market.id, timestamp)
    if latest_orderbook is None:
        return 0

    trades_5m = trades_since(db, market.id, timestamp - timedelta(minutes=5), timestamp)
    contracts_last_5s = trade_count_since(trades_5m, timestamp - timedelta(seconds=5))
    contracts_last_10s = trade_count_since(trades_5m, timestamp - timedelta(seconds=10))
    contracts_last_30s = trade_count_since(trades_5m, timestamp - timedelta(seconds=30))
    contracts_last_60s = trade_count_since(trades_5m, timestamp - timedelta(seconds=60))
    trailing_contracts_5m = sum(trade.count for trade in trades_5m)
    trailing_cpm_5m = trailing_contracts_5m / 5
    expected_contracts_10s = max(trailing_cpm_5m / 6, 0.1)
    flow_spike_ratio = contracts_last_10s / expected_contracts_10s if expected_contracts_10s else None
    taker_yes_last_10s = taker_count_since(trades_5m, timestamp - timedelta(seconds=10), "yes")
    taker_no_last_10s = taker_count_since(trades_5m, timestamp - timedelta(seconds=10), "no")
    taker_side, imbalance = dominant_side(taker_yes_last_10s, taker_no_last_10s)
    previous_orderbook = latest_orderbook_before(db, market.id, timestamp - timedelta(seconds=30))
    depth_change = (
        latest_orderbook.total_depth - previous_orderbook.total_depth
        if previous_orderbook is not None and latest_orderbook.total_depth is not None
        else None
    )
    spread_change = (
        (latest_orderbook.spread or 0) - (previous_orderbook.spread or 0)
        if previous_orderbook is not None and latest_orderbook.spread is not None and previous_orderbook.spread is not None
        else None
    )
    price_change = price_change_for_side(previous_orderbook, latest_orderbook, taker_side)

    common = {
        "contracts_last_5s": contracts_last_5s,
        "contracts_last_10s": contracts_last_10s,
        "contracts_last_30s": contracts_last_30s,
        "contracts_last_60s": contracts_last_60s,
        "trailing_cpm_5m": trailing_cpm_5m,
        "expected_contracts_10s": expected_contracts_10s,
        "flow_spike_ratio": flow_spike_ratio,
        "taker_side": taker_side,
        "taker_side_imbalance": imbalance,
        "taker_yes_last_10s": taker_yes_last_10s,
        "taker_no_last_10s": taker_no_last_10s,
        "best_yes_bid": latest_orderbook.best_yes_bid,
        "best_yes_ask": latest_orderbook.best_yes_ask,
        "best_no_bid": latest_orderbook.best_no_bid,
        "best_no_ask": latest_orderbook.best_no_ask,
        "spread": latest_orderbook.spread,
        "total_depth": latest_orderbook.total_depth,
        "depth_change_after_spike": depth_change,
        "spread_change_after_spike": spread_change,
        "kalshi_price_change_after_spike": price_change,
        "metadata_json": {
            "trade_count_5m": len(trades_5m),
        },
    }

    rows = 0
    if flow_spike_ratio is not None and contracts_last_10s >= LIVE_FLOW_SPIKE_MIN_CONTRACTS_10S and flow_spike_ratio >= LIVE_FLOW_SPIKE_MIN_RATIO:
        rows += insert_signal_once(db, market, timestamp, "live_flow_spike", signal_score=min(100, flow_spike_ratio * 20), common=common)
    if contracts_last_10s >= ONE_SIDED_MIN_CONTRACTS_10S and imbalance is not None and imbalance >= ONE_SIDED_MIN_IMBALANCE:
        rows += insert_signal_once(db, market, timestamp, "one_sided_live_flow", signal_score=min(100, imbalance * 100), common=common)
    if (
        flow_spike_ratio is not None
        and flow_spike_ratio >= LIVE_FLOW_SPIKE_MIN_RATIO
        and price_change is not None
        and abs(price_change) >= PRICE_DRIFT_MIN_CENTS
        and imbalance is not None
        and imbalance >= 0.6
    ):
        rows += insert_signal_once(
            db,
            market,
            timestamp,
            "possible_courtsider_drift",
            signal_score=min(100, abs(price_change) * 15 + flow_spike_ratio * 10),
            common=common,
        )
    if (
        flow_spike_ratio is not None
        and flow_spike_ratio >= LIVE_FLOW_SPIKE_MIN_RATIO
        and contracts_last_10s >= LIVE_FLOW_SPIKE_MIN_CONTRACTS_10S
        and previous_orderbook is not None
        and abs(price_change or 0) <= STALE_MAX_PRICE_CHANGE_CENTS
        and abs(spread_change or 0) <= STALE_MAX_SPREAD_CHANGE_CENTS
    ):
        rows += insert_signal_once(
            db,
            market,
            timestamp,
            "stale_after_flow_spike",
            signal_score=min(100, flow_spike_ratio * 15),
            common=common,
        )
    return rows


def insert_signal_once(
    db: Session,
    market: Market,
    timestamp: datetime,
    signal_type: str,
    signal_score: float,
    common: dict[str, object],
) -> int:
    existing = db.scalar(
        select(LiveMarketSignal)
        .where(
            LiveMarketSignal.market_id == market.id,
            LiveMarketSignal.signal_type == signal_type,
            LiveMarketSignal.timestamp >= timestamp - timedelta(seconds=10),
        )
        .limit(1)
    )
    if existing is not None:
        return 0
    db.add(
        LiveMarketSignal(
            market_id=market.id,
            timestamp=timestamp,
            signal_type=signal_type,
            signal_score=signal_score,
            **common,
        )
    )
    return 1


def trades_since(db: Session, market_id: int, start: datetime, end: datetime) -> list[KalshiTrade]:
    return list(
        db.scalars(
            select(KalshiTrade)
            .where(KalshiTrade.market_id == market_id, KalshiTrade.timestamp >= start, KalshiTrade.timestamp <= end)
            .order_by(KalshiTrade.timestamp)
        )
    )


def latest_orderbook_before(db: Session, market_id: int, timestamp: datetime) -> KalshiOrderbookSnapshot | None:
    return db.scalar(
        select(KalshiOrderbookSnapshot)
        .where(KalshiOrderbookSnapshot.market_id == market_id, KalshiOrderbookSnapshot.timestamp <= timestamp)
        .order_by(desc(KalshiOrderbookSnapshot.timestamp))
        .limit(1)
    )


def trade_count_since(trades: list[KalshiTrade], start: datetime) -> float:
    return sum(trade.count for trade in trades if ensure_aware(trade.timestamp) >= start)


def taker_count_since(trades: list[KalshiTrade], start: datetime, side: str) -> float:
    return sum(trade.count for trade in trades if ensure_aware(trade.timestamp) >= start and (trade.taker_side or "").lower() == side)


def dominant_side(taker_yes: float, taker_no: float) -> tuple[str | None, float | None]:
    total = taker_yes + taker_no
    if total <= 0:
        return None, None
    if taker_yes >= taker_no:
        return "yes", (taker_yes - taker_no) / total
    return "no", (taker_no - taker_yes) / total


def price_change_for_side(
    previous_orderbook: KalshiOrderbookSnapshot | None,
    latest_orderbook: KalshiOrderbookSnapshot,
    side: str | None,
) -> int | None:
    if previous_orderbook is None or side is None:
        return None
    if side == "yes" and previous_orderbook.best_yes_bid is not None and latest_orderbook.best_yes_bid is not None:
        return latest_orderbook.best_yes_bid - previous_orderbook.best_yes_bid
    if side == "no" and previous_orderbook.best_no_bid is not None and latest_orderbook.best_no_bid is not None:
        return latest_orderbook.best_no_bid - previous_orderbook.best_no_bid
    return None


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
