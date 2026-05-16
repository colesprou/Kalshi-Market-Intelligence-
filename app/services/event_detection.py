from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Market, MarketEventDetection, MarketFeatureBucket


def detect_recent_market_events(db: Session, markets: list[Market]) -> int:
    rows = 0
    for market in markets:
        buckets = list(
            db.scalars(
                select(MarketFeatureBucket)
                .where(MarketFeatureBucket.market_id == market.id)
                .order_by(desc(MarketFeatureBucket.bucket_start))
                .limit(8)
            )
        )
        if len(buckets) < 4:
            continue
        ordered = list(reversed(buckets))
        current = ordered[-1]
        previous = ordered[:-1]
        rows += detect_volume_burst(db, market, current, previous)
        rows += detect_one_sided_flow(db, market, current)
        rows += detect_spread_widening(db, market, current, previous)
        rows += detect_liquidity_disappearance(db, market, current, previous)
        rows += detect_top_of_book_sweep(db, market, ordered[-2], current)
    db.commit()
    return rows


def detect_volume_burst(
    db: Session, market: Market, current: MarketFeatureBucket, previous: list[MarketFeatureBucket]
) -> int:
    baseline = avg([bucket.contracts_per_minute for bucket in previous if bucket.contracts_per_minute is not None])
    cpm = current.contracts_per_minute
    if cpm is None or current.volume_delta is None or baseline is None:
        return 0
    threshold = max(20.0, baseline * 3)
    if cpm >= threshold and current.volume_delta >= 50:
        return insert_event_once(
            db,
            market,
            "volume_burst",
            current,
            magnitude=cpm,
            metadata={"contracts_per_minute": cpm, "baseline_cpm": baseline, "volume_delta": current.volume_delta},
        )
    return 0


def detect_one_sided_flow(db: Session, market: Market, current: MarketFeatureBucket) -> int:
    ratio = current.one_sided_flow_ratio
    volume = current.volume_delta
    if ratio is not None and volume is not None and ratio >= 3 and volume >= 50:
        side = "yes" if (current.taker_yes_contracts or 0) > (current.taker_no_contracts or 0) else "no"
        return insert_event_once(
            db,
            market,
            "one_sided_flow",
            current,
            side=side,
            magnitude=ratio,
            metadata={
                "ratio": ratio,
                "volume_delta": volume,
                "taker_yes_contracts": current.taker_yes_contracts,
                "taker_no_contracts": current.taker_no_contracts,
            },
        )
    return 0


def detect_spread_widening(
    db: Session, market: Market, current: MarketFeatureBucket, previous: list[MarketFeatureBucket]
) -> int:
    baseline = avg([bucket.spread for bucket in previous if bucket.spread is not None])
    if current.spread is None or baseline is None:
        return 0
    if current.spread >= max(3, baseline + 2):
        return insert_event_once(
            db,
            market,
            "spread_widening",
            current,
            magnitude=float(current.spread),
            metadata={"spread": current.spread, "baseline_spread": baseline},
        )
    return 0


def detect_liquidity_disappearance(
    db: Session, market: Market, current: MarketFeatureBucket, previous: list[MarketFeatureBucket]
) -> int:
    baseline = avg([bucket.total_depth for bucket in previous if bucket.total_depth is not None])
    if current.total_depth is None or baseline is None or baseline < 500:
        return 0
    decline = 1 - (current.total_depth / baseline)
    if decline >= 0.5:
        return insert_event_once(
            db,
            market,
            "liquidity_disappearance",
            current,
            magnitude=decline,
            metadata={"total_depth": current.total_depth, "baseline_depth": baseline, "decline": decline},
        )
    return 0


def detect_top_of_book_sweep(
    db: Session, market: Market, previous: MarketFeatureBucket, current: MarketFeatureBucket
) -> int:
    events = 0
    if previous.best_yes_bid is not None and current.best_yes_bid is not None and current.best_yes_bid <= previous.best_yes_bid - 2:
        events += insert_event_once(
            db,
            market,
            "top_of_book_sweep",
            current,
            side="yes",
            magnitude=float(previous.best_yes_bid - current.best_yes_bid),
            metadata={"previous_best_yes_bid": previous.best_yes_bid, "current_best_yes_bid": current.best_yes_bid},
        )
    if previous.best_no_bid is not None and current.best_no_bid is not None and current.best_no_bid <= previous.best_no_bid - 2:
        events += insert_event_once(
            db,
            market,
            "top_of_book_sweep",
            current,
            side="no",
            magnitude=float(previous.best_no_bid - current.best_no_bid),
            metadata={"previous_best_no_bid": previous.best_no_bid, "current_best_no_bid": current.best_no_bid},
        )
    return events


def insert_event_once(
    db: Session,
    market: Market,
    event_type: str,
    bucket: MarketFeatureBucket,
    magnitude: float,
    metadata: dict[str, object],
    side: str | None = None,
) -> int:
    existing = db.scalar(
        select(MarketEventDetection)
        .where(
            MarketEventDetection.market_id == market.id,
            MarketEventDetection.event_type == event_type,
            MarketEventDetection.started_at >= bucket.bucket_start - timedelta(minutes=2),
            MarketEventDetection.started_at <= bucket.bucket_start,
            MarketEventDetection.side == side,
        )
        .limit(1)
    )
    if existing is not None:
        return 0
    db.add(
        MarketEventDetection(
            market_id=market.id,
            event_type=event_type,
            started_at=bucket.bucket_start,
            ended_at=bucket.bucket_start + timedelta(seconds=bucket.bucket_seconds),
            duration_seconds=float(bucket.bucket_seconds),
            side=side,
            magnitude=magnitude,
            metadata_json=metadata,
        )
    )
    return 1


def avg(values: list[float | int]) -> float | None:
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)
