from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    KalshiOrderbookSnapshot,
    KalshiPrivateFill,
    KalshiTrade,
    Market,
    MarketFeatureBucket,
    SharpBookOddsSnapshot,
)
from app.services.metrics import calculate_orderbook_imbalance, consensus_fair_probability


BUCKET_SECONDS = 60


@dataclass(frozen=True)
class BucketWindow:
    start: datetime
    end: datetime
    seconds: int = BUCKET_SECONDS


def floor_minute(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def build_recent_feature_buckets(db: Session, markets: list[Market], now: datetime | None = None) -> int:
    current = floor_minute(now or datetime.now(timezone.utc))
    rows = 0
    for market in markets:
        if upsert_feature_bucket(db, market, BucketWindow(start=current, end=current + timedelta(seconds=BUCKET_SECONDS))):
            rows += 1
    db.commit()
    return rows


def backfill_feature_buckets(
    db: Session,
    markets: list[Market],
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    rows = 0
    for market in markets:
        market_start, market_end = market_bucket_bounds(db, market, start, end)
        if market_start is None or market_end is None:
            continue
        bucket_start = floor_minute(market_start)
        final_start = floor_minute(market_end)
        while bucket_start <= final_start:
            if upsert_feature_bucket(
                db,
                market,
                BucketWindow(start=bucket_start, end=bucket_start + timedelta(seconds=BUCKET_SECONDS)),
            ):
                rows += 1
            bucket_start += timedelta(seconds=BUCKET_SECONDS)
        db.commit()
    return rows


def market_bucket_bounds(
    db: Session, market: Market, requested_start: datetime | None, requested_end: datetime | None
) -> tuple[datetime | None, datetime | None]:
    first_snapshot = db.scalar(
        select(KalshiOrderbookSnapshot)
        .where(KalshiOrderbookSnapshot.market_id == market.id)
        .order_by(KalshiOrderbookSnapshot.timestamp)
        .limit(1)
    )
    last_snapshot = db.scalar(
        select(KalshiOrderbookSnapshot)
        .where(KalshiOrderbookSnapshot.market_id == market.id)
        .order_by(desc(KalshiOrderbookSnapshot.timestamp))
        .limit(1)
    )
    if first_snapshot is None or last_snapshot is None:
        return None, None
    start = requested_start or first_snapshot.timestamp
    end = requested_end or last_snapshot.timestamp
    return start, end


def upsert_feature_bucket(db: Session, market: Market, window: BucketWindow) -> bool:
    orderbook = latest_orderbook_in_window(db, market.id, window)
    trades = trades_in_window(db, market.id, window)
    sharp_odds = sharp_odds_before(db, market.id, window.end)
    fills = fills_in_window(db, market.id, window)
    previous_bucket = latest_bucket_before(db, market.id, window.start)
    previous_orderbook = latest_orderbook_before(db, market.id, window.start)

    if orderbook is None and not trades and not sharp_odds and not fills:
        return False

    fair_yes_probability = consensus_fair_probability(sharp_odds)
    fair_yes = fair_yes_probability * 100 if fair_yes_probability is not None else None
    fair_no = 100 - fair_yes if fair_yes is not None else None
    taker_yes = sum(trade.count for trade in trades if (trade.taker_side or "").lower() == "yes")
    taker_no = sum(trade.count for trade in trades if (trade.taker_side or "").lower() == "no")
    trade_volume = taker_yes + taker_no
    volume_delta = volume_delta_from_orderbooks(orderbook, previous_orderbook)
    used_volume_fallback = trade_volume <= 0 and volume_delta is not None
    effective_volume = trade_volume if trade_volume > 0 else volume_delta
    cpm = effective_volume / (window.seconds / 60) if effective_volume is not None else None
    previous_cpm = previous_bucket.contracts_per_minute if previous_bucket else None
    volume_acceleration = cpm - previous_cpm if cpm is not None and previous_cpm is not None else None
    one_sided_ratio = one_sided_flow_ratio(taker_yes, taker_no)
    depth_at_best_yes = depth_at_price(orderbook.yes_book, orderbook.best_yes_bid) if orderbook else None
    depth_at_best_no = depth_at_price(orderbook.no_book, orderbook.best_no_bid) if orderbook else None
    fill_evs = fill_ev_values(fills, fair_yes, fair_no)

    bucket = db.scalar(
        select(MarketFeatureBucket).where(
            MarketFeatureBucket.market_id == market.id,
            MarketFeatureBucket.bucket_start == window.start,
            MarketFeatureBucket.bucket_seconds == window.seconds,
        )
    )
    if bucket is None:
        bucket = MarketFeatureBucket(market_id=market.id, bucket_start=window.start, bucket_seconds=window.seconds)
        db.add(bucket)

    bucket.sport = market.sport
    bucket.league = market.league
    bucket.market_type = market.market_type
    bucket.time_to_event_minutes = time_to_event_minutes(market, window.start)
    bucket.day_of_week = window.start.weekday()
    bucket.hour_of_day = window.start.hour
    bucket.best_yes_bid = orderbook.best_yes_bid if orderbook else None
    bucket.best_no_bid = orderbook.best_no_bid if orderbook else None
    bucket.consensus_fair_yes = fair_yes
    bucket.consensus_fair_no = fair_no
    bucket.edge_yes_at_bid = fair_yes - orderbook.best_yes_bid if orderbook and fair_yes is not None and orderbook.best_yes_bid is not None else None
    bucket.edge_no_at_bid = fair_no - orderbook.best_no_bid if orderbook and fair_no is not None and orderbook.best_no_bid is not None else None
    bucket.volume_delta = effective_volume
    bucket.contracts_per_minute = cpm
    bucket.taker_yes_contracts = taker_yes
    bucket.taker_no_contracts = taker_no
    bucket.one_sided_flow_ratio = one_sided_ratio
    bucket.volume_acceleration = volume_acceleration
    bucket.spread = orderbook.spread if orderbook else None
    bucket.total_depth = orderbook.total_depth if orderbook else None
    bucket.depth_at_best_yes = depth_at_best_yes
    bucket.depth_at_best_no = depth_at_best_no
    bucket.orderbook_imbalance = calculate_orderbook_imbalance(orderbook) if orderbook else None
    bucket.ev_at_best_yes_bid = bucket.edge_yes_at_bid
    bucket.ev_at_best_no_bid = bucket.edge_no_at_bid
    bucket.actual_fill_count = len(fills)
    bucket.avg_ev_at_fill = sum(fill_evs) / len(fill_evs) if fill_evs else None
    bucket.source_quality_flags = {
        "has_orderbook": orderbook is not None,
        "has_trade_tape": bool(trades),
        "has_sharp_consensus": fair_yes is not None,
        "has_volume_fallback": volume_delta is not None,
        "has_private_fills": bool(fills),
        "used_volume_fallback_for_cpm": used_volume_fallback,
        "partial_bucket": window.end > datetime.now(timezone.utc),
    }
    return True


def latest_orderbook_in_window(db: Session, market_id: int, window: BucketWindow) -> KalshiOrderbookSnapshot | None:
    return db.scalar(
        select(KalshiOrderbookSnapshot)
        .where(
            KalshiOrderbookSnapshot.market_id == market_id,
            KalshiOrderbookSnapshot.timestamp >= window.start,
            KalshiOrderbookSnapshot.timestamp < window.end,
        )
        .order_by(desc(KalshiOrderbookSnapshot.timestamp))
        .limit(1)
    )


def latest_orderbook_before(db: Session, market_id: int, before: datetime) -> KalshiOrderbookSnapshot | None:
    return db.scalar(
        select(KalshiOrderbookSnapshot)
        .where(KalshiOrderbookSnapshot.market_id == market_id, KalshiOrderbookSnapshot.timestamp < before)
        .order_by(desc(KalshiOrderbookSnapshot.timestamp))
        .limit(1)
    )


def latest_bucket_before(db: Session, market_id: int, before: datetime) -> MarketFeatureBucket | None:
    return db.scalar(
        select(MarketFeatureBucket)
        .where(MarketFeatureBucket.market_id == market_id, MarketFeatureBucket.bucket_start < before)
        .order_by(desc(MarketFeatureBucket.bucket_start))
        .limit(1)
    )


def trades_in_window(db: Session, market_id: int, window: BucketWindow) -> list[KalshiTrade]:
    return list(
        db.scalars(
            select(KalshiTrade)
            .where(KalshiTrade.market_id == market_id, KalshiTrade.timestamp >= window.start, KalshiTrade.timestamp < window.end)
            .order_by(KalshiTrade.timestamp)
        )
    )


def fills_in_window(db: Session, market_id: int, window: BucketWindow) -> list[KalshiPrivateFill]:
    return list(
        db.scalars(
            select(KalshiPrivateFill).where(
                KalshiPrivateFill.market_id == market_id,
                KalshiPrivateFill.timestamp >= window.start,
                KalshiPrivateFill.timestamp < window.end,
            )
        )
    )


def sharp_odds_before(db: Session, market_id: int, before: datetime) -> list[SharpBookOddsSnapshot]:
    return list(
        db.scalars(
            select(SharpBookOddsSnapshot)
            .where(
                SharpBookOddsSnapshot.market_id == market_id,
                SharpBookOddsSnapshot.timestamp >= before - timedelta(minutes=10),
                SharpBookOddsSnapshot.timestamp <= before,
            )
            .order_by(SharpBookOddsSnapshot.timestamp)
        )
    )


def volume_delta_from_orderbooks(
    orderbook: KalshiOrderbookSnapshot | None, previous_orderbook: KalshiOrderbookSnapshot | None
) -> float | None:
    if orderbook is None or orderbook.volume is None or previous_orderbook is None or previous_orderbook.volume is None:
        return None
    return float(max(0, orderbook.volume - previous_orderbook.volume))


def one_sided_flow_ratio(taker_yes: float, taker_no: float) -> float | None:
    total = taker_yes + taker_no
    if total <= 0:
        return None
    smaller = min(taker_yes, taker_no)
    larger = max(taker_yes, taker_no)
    return larger / max(smaller, 1.0)


def depth_at_price(book: dict[str, int] | None, price: int | None) -> int | None:
    if book is None or price is None:
        return None
    return book.get(str(price), 0)


def fill_ev_values(fills: list[KalshiPrivateFill], fair_yes: float | None, fair_no: float | None) -> list[float]:
    values: list[float] = []
    for fill in fills:
        if fill.price is None:
            continue
        side = (fill.side or "").lower()
        if side == "yes" and fair_yes is not None:
            values.append(fair_yes - fill.price)
        elif side == "no" and fair_no is not None:
            values.append(fair_no - fill.price)
    return values


def time_to_event_minutes(market: Market, bucket_start: datetime) -> float | None:
    if market.event_start_time is None:
        return None
    event_start = market.event_start_time
    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    return (event_start - bucket_start).total_seconds() / 60
