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


class KalshiTradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    trade_id: str
    timestamp: datetime
    count: float
    yes_price: int | None
    no_price: int | None
    taker_side: str | None
    taker_book_side: str | None


class MarketFeatureBucketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    bucket_start: datetime
    bucket_seconds: int
    sport: str | None
    league: str | None
    market_type: str | None
    time_to_event_minutes: float | None
    day_of_week: int | None
    hour_of_day: int | None
    best_yes_bid: int | None
    best_no_bid: int | None
    consensus_fair_yes: float | None
    consensus_fair_no: float | None
    edge_yes_at_bid: float | None
    edge_no_at_bid: float | None
    volume_delta: float | None
    contracts_per_minute: float | None
    taker_yes_contracts: float | None
    taker_no_contracts: float | None
    one_sided_flow_ratio: float | None
    volume_acceleration: float | None
    spread: int | None
    total_depth: int | None
    depth_at_best_yes: int | None
    depth_at_best_no: int | None
    orderbook_imbalance: float | None
    ev_at_best_yes_bid: float | None
    ev_at_best_no_bid: float | None
    actual_fill_count: int
    avg_ev_at_fill: float | None
    source_quality_flags: dict[str, Any] | None


class MarketEventDetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    event_type: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    side: str | None
    magnitude: float | None
    metadata_json: dict[str, Any] | None


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
