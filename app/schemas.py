from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MarketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    sport: str | None
    league: str | None
    market_type: str | None
    event_title: str | None
    event_start_time: datetime | None
    status: str | None
    created_at: datetime
    updated_at: datetime


class OrderbookSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    timestamp: datetime
    best_yes_bid: int | None
    best_yes_ask: int | None
    best_no_bid: int | None
    best_no_ask: int | None
    yes_bid_depth: int
    yes_ask_depth: int
    no_bid_depth: int
    no_ask_depth: int
    total_depth: int
    spread: int | None
    contracts_per_minute: float | None
    volume: int | None
    yes_book: dict[str, int] | None
    no_book: dict[str, int] | None


class DerivedMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    timestamp: datetime
    consensus_fair_probability: float | None
    consensus_fair_price: int | None
    edge_yes: float | None
    edge_no: float | None
    spread: int | None
    volatility_score: float | None
    sharp_move_score: float | None
    liquidity_score: float | None
    contracts_per_minute: float | None
    time_to_event_minutes: float | None
    orderbook_imbalance: float | None
    liquidity_stability: float | None
    kalshi_lag_seconds: float | None


class SharpBookOddsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    timestamp: datetime
    sportsbook: str
    side: str
    american_odds: int
    decimal_odds: float
    implied_probability: float
    devigged_probability: float | None


class SharpBookLimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    timestamp: datetime
    sportsbook: str
    side: str
    limit_amount: float | None


class OpportunityScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    timestamp: datetime
    queue_positioning_score: float
    stale_opportunity_score: float
    market_making_score: float
    maker_stress_score: float
    notes_json: dict[str, Any] | None


class OpportunityRead(BaseModel):
    market: MarketRead
    score: OpportunityScoreRead
    metric: DerivedMetricRead | None = None


class HealthRead(BaseModel):
    status: str
