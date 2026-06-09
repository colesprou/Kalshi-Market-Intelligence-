from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    DerivedMarketMetric,
    JobRun,
    KalshiOrderbookSnapshot,
    KalshiTrade,
    Market,
    OpportunityScore,
    SharpBookLimitsSnapshot,
    SharpBookOddsSnapshot,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        league: str | None = None,
        market_type: str | None = None,
    ) -> list[Market]:
        stmt = select(Market).order_by(Market.event_start_time, Market.ticker).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Market.status == status)
        if league:
            stmt = stmt.where(func.lower(Market.league) == league.lower())
        if market_type:
            stmt = stmt.where(Market.market_type == market_type)
        return list(self.db.scalars(stmt))

    def by_ticker(self, ticker: str) -> Market | None:
        return self.db.scalar(select(Market).where(Market.ticker == ticker))

    def upsert_market(
        self,
        ticker: str,
        sport: str | None = None,
        league: str | None = None,
        market_type: str | None = None,
        event_title: str | None = None,
        event_start_time: datetime | None = None,
        status: str | None = None,
        optic_fixture_id: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> Market:
        market = self.by_ticker(ticker)
        if market is None:
            market = Market(ticker=ticker)
            self.db.add(market)
        market.sport = sport or market.sport
        market.league = league or market.league
        market.market_type = market_type or market.market_type
        market.event_title = event_title or market.event_title
        market.event_start_time = event_start_time or market.event_start_time
        market.status = status or market.status
        market.optic_fixture_id = optic_fixture_id or market.optic_fixture_id
        market.raw_payload = raw_payload or market.raw_payload
        return market

    def active_for_polling(self, limit: int = 1000) -> list[Market]:
        stmt = (
            select(Market)
            .where(Market.status.in_(["open", "active", "unplayed", "live"]))
            .order_by(Market.event_start_time.nulls_last(), Market.ticker)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def fast_poll_candidates(self, limit: int, window_minutes: int, activity_window_seconds: int = 300) -> list[Market]:
        now = utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        window_end = now + timedelta(minutes=window_minutes)
        activity_start = now - timedelta(seconds=activity_window_seconds)
        stmt = (
            select(Market)
            .where(Market.status.in_(["open", "active", "unplayed", "live"]))
            .order_by(Market.event_start_time.nulls_last(), Market.ticker)
            .limit(max(limit * 8, 100))
        )
        candidates = list(self.db.scalars(stmt))
        ranked: list[tuple[float, Market]] = []
        for market in candidates:
            score = self._fast_poll_activity_score(
                market=market,
                now=now,
                window_start=window_start,
                window_end=window_end,
                activity_start=activity_start,
            )
            if score > 0:
                ranked.append((score, market))
        ranked.sort(key=lambda item: (-item[0], item[1].event_start_time or datetime.max.replace(tzinfo=timezone.utc), item[1].ticker))
        return [market for _, market in ranked[:limit]]

    def _fast_poll_activity_score(
        self,
        market: Market,
        now: datetime,
        window_start: datetime,
        window_end: datetime,
        activity_start: datetime,
    ) -> float:
        status = (market.status or "").lower()
        score = 0.0
        if status == "live":
            score += 1000
        elif status == "active":
            score += 50

        recent_trade_count = self.db.scalar(
            select(KalshiTrade.count)
            .where(KalshiTrade.market_id == market.id, KalshiTrade.timestamp >= activity_start)
            .limit(1)
        )
        if recent_trade_count is not None:
            score += 500

        recent_orderbooks = list(
            self.db.scalars(
                select(KalshiOrderbookSnapshot)
                .where(
                    KalshiOrderbookSnapshot.market_id == market.id,
                    KalshiOrderbookSnapshot.timestamp >= activity_start,
                )
                .order_by(desc(KalshiOrderbookSnapshot.timestamp))
                .limit(2)
            )
        )
        if len(recent_orderbooks) >= 2:
            latest, previous = recent_orderbooks[0], recent_orderbooks[1]
            if latest.volume is not None and previous.volume is not None and latest.volume > previous.volume:
                score += 400 + min(100, latest.volume - previous.volume)
            if quote_changed(latest, previous):
                score += 250
            if latest.total_depth != previous.total_depth:
                score += 150
        elif len(recent_orderbooks) == 1 and status in {"live", "active"}:
            score += 25

        if market.event_start_time is not None and window_start <= ensure_aware(market.event_start_time) <= window_end:
            score += 20
        return score


def quote_changed(latest: KalshiOrderbookSnapshot, previous: KalshiOrderbookSnapshot) -> bool:
    return (
        latest.best_yes_bid != previous.best_yes_bid
        or latest.best_yes_ask != previous.best_yes_ask
        or latest.best_no_bid != previous.best_no_bid
        or latest.best_no_ask != previous.best_no_ask
        or latest.spread != previous.spread
    )


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class SnapshotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_orderbook(self, market_id: int) -> KalshiOrderbookSnapshot | None:
        return self.db.scalar(
            select(KalshiOrderbookSnapshot)
            .where(KalshiOrderbookSnapshot.market_id == market_id)
            .order_by(desc(KalshiOrderbookSnapshot.timestamp))
            .limit(1)
        )

    def orderbooks_since(self, market_id: int, since: datetime) -> list[KalshiOrderbookSnapshot]:
        return list(
            self.db.scalars(
                select(KalshiOrderbookSnapshot)
                .where(
                    KalshiOrderbookSnapshot.market_id == market_id,
                    KalshiOrderbookSnapshot.timestamp >= since,
                )
                .order_by(KalshiOrderbookSnapshot.timestamp)
            )
        )

    def latest_metric(self, market_id: int) -> DerivedMarketMetric | None:
        return self.db.scalar(
            select(DerivedMarketMetric)
            .where(DerivedMarketMetric.market_id == market_id)
            .order_by(desc(DerivedMarketMetric.timestamp))
            .limit(1)
        )

    def latest_score(self, market_id: int) -> OpportunityScore | None:
        return self.db.scalar(
            select(OpportunityScore)
            .where(OpportunityScore.market_id == market_id)
            .order_by(desc(OpportunityScore.timestamp))
            .limit(1)
        )

    def latest_sharp_odds(self, market_id: int, window_minutes: int = 10) -> list[SharpBookOddsSnapshot]:
        since = utcnow() - timedelta(minutes=window_minutes)
        return list(
            self.db.scalars(
                select(SharpBookOddsSnapshot)
                .where(SharpBookOddsSnapshot.market_id == market_id, SharpBookOddsSnapshot.timestamp >= since)
                .order_by(SharpBookOddsSnapshot.timestamp)
            )
        )

    def latest_limits(self, market_id: int, window_minutes: int = 15) -> list[SharpBookLimitsSnapshot]:
        since = utcnow() - timedelta(minutes=window_minutes)
        return list(
            self.db.scalars(
                select(SharpBookLimitsSnapshot)
                .where(SharpBookLimitsSnapshot.market_id == market_id, SharpBookLimitsSnapshot.timestamp >= since)
                .order_by(desc(SharpBookLimitsSnapshot.timestamp))
            )
        )


class JobRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start(self, job_name: str) -> JobRun:
        run = JobRun(job_name=job_name, started_at=utcnow(), status="running", rows_inserted=0)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish(self, run: JobRun, status: str, rows_inserted: int = 0, error_message: str | None = None) -> None:
        finished_at = utcnow()
        started_at = run.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        run.finished_at = finished_at
        run.status = status
        run.rows_inserted = rows_inserted
        run.duration_seconds = (finished_at - started_at).total_seconds()
        run.error_message = error_message
        self.db.commit()
