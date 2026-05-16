from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
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
from app.repositories import MarketRepository, SnapshotRepository
from app.schemas import (
    DerivedMetricRead,
    HealthRead,
    KalshiTradeRead,
    LiveMarketSignalRead,
    MarketRead,
    MarketEventDetectionRead,
    MarketFeatureBucketRead,
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


@router.get("/markets", response_model=list[MarketRead])
def list_markets(
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[Market]:
    return MarketRepository(db).list(limit=limit, offset=offset, status=status)


@router.get("/markets/{ticker}", response_model=MarketRead)
def get_market(ticker: str, db: Session = Depends(get_db)) -> Market:
    market = MarketRepository(db).by_ticker(ticker)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


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
