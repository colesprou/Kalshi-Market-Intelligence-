from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    DerivedMarketMetric,
    KalshiTrade,
    KalshiOrderbookSnapshot,
    LiveMarketSignal,
    Market,
    MarketEventDetection,
    MarketFeatureBucket,
    OpportunityScore,
    SharpBookLimitsSnapshot,
    SharpBookOddsSnapshot,
)
from app.repositories import MarketRepository, SnapshotRepository, utcnow
from app.schemas import (
    DerivedMetricRead,
    HealthRead,
    KalshiTradeRead,
    LiveMarketSignalRead,
    MarketRead,
    MarketEventDetectionRead,
    MarketFeatureBucketRead,
    MarketVolumeSummaryRead,
    OpportunityRead,
    OpportunityScoreRead,
    OrderbookSnapshotRead,
    SharpBookLimitRead,
    SharpBookOddsRead,
)

router = APIRouter()


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok")


def markets_with_volume_windows(db: Session, markets: list[Market]) -> list[dict[str, object]]:
    if not markets:
        return []

    market_ids = [market.id for market in markets]
    now = utcnow()
    volume_total = latest_market_volumes(db, market_ids)
    volume_30m = recent_market_volumes(db, market_ids, now, minutes=30)
    volume_1h = recent_market_volumes(db, market_ids, now, minutes=60)
    volume_3h = recent_market_volumes(db, market_ids, now, minutes=180)

    rows: list[dict[str, object]] = []
    for market in markets:
        item = MarketRead.model_validate(market).model_dump()
        item["volume_total"] = volume_total.get(market.id)
        item["volume_last_30m"] = volume_30m.get(market.id, 0.0)
        item["volume_last_1h"] = volume_1h.get(market.id, 0.0)
        item["volume_last_3h"] = volume_3h.get(market.id, 0.0)
        item["yes_label"] = side_label_from_market(market, "yes")
        item["no_label"] = side_label_from_market(market, "no")
        rows.append(item)
    return rows


def latest_market_volumes(db: Session, market_ids: list[int]) -> dict[int, int]:
    latest = (
        select(
            KalshiOrderbookSnapshot.market_id.label("market_id"),
            func.max(KalshiOrderbookSnapshot.timestamp).label("timestamp"),
        )
        .where(KalshiOrderbookSnapshot.market_id.in_(market_ids))
        .group_by(KalshiOrderbookSnapshot.market_id)
        .subquery()
    )
    rows = db.execute(
        select(KalshiOrderbookSnapshot.market_id, KalshiOrderbookSnapshot.volume)
        .join(
            latest,
            (KalshiOrderbookSnapshot.market_id == latest.c.market_id)
            & (KalshiOrderbookSnapshot.timestamp == latest.c.timestamp),
        )
        .where(KalshiOrderbookSnapshot.volume.isnot(None))
    )
    return {market_id: int(volume) for market_id, volume in rows if volume is not None}


def recent_market_volumes(db: Session, market_ids: list[int], now, minutes: int) -> dict[int, float]:
    since = now - timedelta(minutes=minutes)
    trade_rows = db.execute(
        select(KalshiTrade.market_id, func.coalesce(func.sum(KalshiTrade.count), 0.0))
        .where(KalshiTrade.market_id.in_(market_ids), KalshiTrade.timestamp >= since)
        .group_by(KalshiTrade.market_id)
    )
    volumes = {market_id: float(volume or 0) for market_id, volume in trade_rows}

    feature_rows = db.execute(
        select(MarketFeatureBucket.market_id, func.coalesce(func.sum(MarketFeatureBucket.volume_delta), 0.0))
        .where(MarketFeatureBucket.market_id.in_(market_ids), MarketFeatureBucket.bucket_start >= since)
        .group_by(MarketFeatureBucket.market_id)
    )
    for market_id, volume in feature_rows:
        volumes[market_id] = max(volumes.get(market_id, 0.0), float(volume or 0))
    return volumes


def side_trade_volume(
    db: Session,
    market: Market,
    side: str,
    start,
    end,
) -> float:
    stmt = select(func.coalesce(func.sum(KalshiTrade.count), 0.0)).where(
        KalshiTrade.market_id == market.id,
        func.lower(KalshiTrade.taker_side) == side,
    )
    if start is not None:
        stmt = stmt.where(KalshiTrade.timestamp >= start)
    if end is not None:
        stmt = stmt.where(KalshiTrade.timestamp <= end)
    return float(db.scalar(stmt) or 0.0)


def side_label_from_market(market: Market, side: str) -> str | None:
    raw_payload = market.raw_payload or {}
    side = side.lower()
    candidates = (
        ("yes_sub_title", "yes_title", "yes_label", "yes"),
        ("no_sub_title", "no_title", "no_label", "no"),
    )
    keys = candidates[0] if side == "yes" else candidates[1]
    for key in keys:
        value = raw_payload.get(key)
        if value:
            return str(value)
    optic_odds = raw_payload.get("optic_kalshi_odds") or {}
    if side == "yes":
        value = optic_odds.get("selection") or optic_odds.get("name")
        if value:
            return str(value)
    if (market.market_type or "").upper() in {"KXITFMATCH", "KXATPMATCH", "KXWTAMATCH"}:
        return side.upper()
    return None


@router.get("/markets", response_model=list[MarketRead])
def list_markets(
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    league: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    markets = MarketRepository(db).list(
        limit=limit,
        offset=offset,
        status=status,
        league=league,
        market_type=market_type,
    )
    return markets_with_volume_windows(db, markets)


@router.get("/markets/{ticker}", response_model=MarketRead)
def get_market(ticker: str, db: Session = Depends(get_db)) -> dict[str, object]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    item = MarketRead.model_validate(market).model_dump()
    item["volume_total"] = latest_market_volumes(db, [market.id]).get(market.id)
    item["volume_last_30m"] = recent_market_volumes(db, [market.id], utcnow(), minutes=30).get(market.id, 0.0)
    item["volume_last_1h"] = recent_market_volumes(db, [market.id], utcnow(), minutes=60).get(market.id, 0.0)
    item["volume_last_3h"] = recent_market_volumes(db, [market.id], utcnow(), minutes=180).get(market.id, 0.0)
    item["yes_label"] = side_label_from_market(market, "yes")
    item["no_label"] = side_label_from_market(market, "no")
    return item


@router.get("/markets/{ticker}/volume-summary", response_model=list[MarketVolumeSummaryRead])
def get_market_volume_summary(ticker: str, db: Session = Depends(get_db)) -> list[MarketVolumeSummaryRead]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    now = utcnow()
    latest_volume = latest_market_volumes(db, [market.id]).get(market.id)
    latest_trade_at = db.scalar(
        select(func.max(KalshiTrade.timestamp)).where(KalshiTrade.market_id == market.id)
    )
    rows = []
    for side in ("yes", "no"):
        rows.append(
            MarketVolumeSummaryRead(
                ticker=market.ticker,
                side=side,
                label=side_label_from_market(market, side),
                volume_total=latest_volume,
                contracts_30m=side_trade_volume(db, market, side, now - timedelta(minutes=30), now),
                contracts_1h=side_trade_volume(db, market, side, now - timedelta(hours=1), now),
                contracts_3h=side_trade_volume(db, market, side, now - timedelta(hours=3), now),
                contracts_pregame=side_trade_volume(db, market, side, None, market.event_start_time),
                latest_trade_at=latest_trade_at,
            )
        )
    return rows


@router.get("/markets/{ticker}/metrics", response_model=list[DerivedMetricRead])
def get_market_metrics(
    ticker: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[DerivedMarketMetric]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return list(
        db.scalars(
            select(DerivedMarketMetric)
            .where(DerivedMarketMetric.market_id == market.id)
            .order_by(desc(DerivedMarketMetric.timestamp))
            .limit(limit)
        )
    )


@router.get("/markets/{ticker}/orderbooks", response_model=list[OrderbookSnapshotRead])
def get_market_orderbooks(
    ticker: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[KalshiOrderbookSnapshot]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return list(
        db.scalars(
            select(KalshiOrderbookSnapshot)
            .where(KalshiOrderbookSnapshot.market_id == market.id)
            .order_by(desc(KalshiOrderbookSnapshot.timestamp))
            .limit(limit)
        )
    )


@router.get("/markets/{ticker}/sharp-odds", response_model=list[SharpBookOddsRead])
def get_market_sharp_odds(
    ticker: str,
    limit: int = Query(default=300, ge=1, le=2000),
    side: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SharpBookOddsSnapshot]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    stmt = (
        select(SharpBookOddsSnapshot)
        .where(SharpBookOddsSnapshot.market_id == market.id)
        .order_by(desc(SharpBookOddsSnapshot.timestamp))
        .limit(limit)
    )
    if side:
        stmt = stmt.where(SharpBookOddsSnapshot.side == side)
    return list(db.scalars(stmt))


@router.get("/markets/{ticker}/limits", response_model=list[SharpBookLimitRead])
def get_market_limits(
    ticker: str,
    limit: int = Query(default=300, ge=1, le=2000),
    sportsbook: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SharpBookLimitsSnapshot]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    stmt = (
        select(SharpBookLimitsSnapshot)
        .where(SharpBookLimitsSnapshot.market_id == market.id)
        .order_by(desc(SharpBookLimitsSnapshot.timestamp))
        .limit(limit)
    )
    if sportsbook:
        stmt = stmt.where(SharpBookLimitsSnapshot.sportsbook == sportsbook)
    return list(db.scalars(stmt))


@router.get("/markets/{ticker}/trades", response_model=list[KalshiTradeRead])
def get_market_trades(
    ticker: str,
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[KalshiTrade]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return list(
        db.scalars(
            select(KalshiTrade)
            .where(KalshiTrade.market_id == market.id)
            .order_by(desc(KalshiTrade.timestamp))
            .limit(limit)
        )
    )


@router.get("/markets/{ticker}/features", response_model=list[MarketFeatureBucketRead])
def get_market_features(
    ticker: str,
    bucket_seconds: int = Query(default=60, ge=1, le=3600),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[MarketFeatureBucket]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return list(
        db.scalars(
            select(MarketFeatureBucket)
            .where(
                MarketFeatureBucket.market_id == market.id,
                MarketFeatureBucket.bucket_seconds == bucket_seconds,
            )
            .order_by(desc(MarketFeatureBucket.bucket_start))
            .limit(limit)
        )
    )


@router.get("/markets/{ticker}/events", response_model=list[MarketEventDetectionRead])
def get_market_events(
    ticker: str,
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[MarketEventDetection]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    stmt = (
        select(MarketEventDetection)
        .where(MarketEventDetection.market_id == market.id)
        .order_by(desc(MarketEventDetection.started_at))
        .limit(limit)
    )
    if event_type:
        stmt = stmt.where(MarketEventDetection.event_type == event_type)
    return list(db.scalars(stmt))


@router.get("/markets/{ticker}/live-signals", response_model=list[LiveMarketSignalRead])
def get_market_live_signals(
    ticker: str,
    signal_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[LiveMarketSignal]:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    stmt = (
        select(LiveMarketSignal)
        .where(LiveMarketSignal.market_id == market.id)
        .order_by(desc(LiveMarketSignal.timestamp))
        .limit(limit)
    )
    if signal_type:
        stmt = stmt.where(LiveMarketSignal.signal_type == signal_type)
    return list(db.scalars(stmt))


@router.get("/scores/{ticker}", response_model=OpportunityScoreRead)
def get_scores(ticker: str, db: Session = Depends(get_db)) -> OpportunityScore:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    score = SnapshotRepository(db).latest_score(market.id)
    if score is None:
        raise HTTPException(status_code=404, detail="Scores not found")
    return score


@router.get("/opportunities", response_model=list[OpportunityRead])
def opportunities(
    kind: Literal["stale", "market-making", "queue-positioning", "stress"] | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OpportunityRead]:
    score_column = OpportunityScore.stale_opportunity_score
    if kind == "market-making":
        score_column = OpportunityScore.market_making_score
    elif kind == "queue-positioning":
        score_column = OpportunityScore.queue_positioning_score
    elif kind == "stress":
        score_column = OpportunityScore.maker_stress_score

    rows = db.execute(
        select(Market, OpportunityScore)
        .join(OpportunityScore, OpportunityScore.market_id == Market.id)
        .order_by(desc(score_column), desc(OpportunityScore.timestamp))
        .limit(limit)
    ).all()

    payload: list[OpportunityRead] = []
    snapshots = SnapshotRepository(db)
    for market, score in rows:
        payload.append(
            OpportunityRead(
                market=MarketRead.model_validate(market),
                score=OpportunityScoreRead.model_validate(score),
                metric=(
                    DerivedMetricRead.model_validate(metric)
                    if (metric := snapshots.latest_metric(market.id)) is not None
                    else None
                ),
            )
        )
    return payload


@router.get("/opportunities/stale", response_model=list[OpportunityRead])
def stale_opportunities(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[OpportunityRead]:
    return opportunities(kind="stale", limit=limit, db=db)


@router.get("/opportunities/market-making", response_model=list[OpportunityRead])
def market_making_opportunities(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[OpportunityRead]:
    return opportunities(kind="market-making", limit=limit, db=db)


@router.get("/opportunities/queue-positioning", response_model=list[OpportunityRead])
def queue_positioning_opportunities(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[OpportunityRead]:
    return opportunities(kind="queue-positioning", limit=limit, db=db)
