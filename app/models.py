from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Market(TimestampMixin, Base):
    __tablename__ = "markets"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(128), unique=True, index=True, nullable=False)
    sport = Column(String(64), index=True)
    league = Column(String(64), index=True)
    market_type = Column(String(64), index=True)
    event_title = Column(Text)
    event_start_time = Column(DateTime(timezone=True), index=True)
    status = Column(String(32), index=True)
    optic_fixture_id = Column(String(128), index=True)
    raw_payload = Column(JSON)

    orderbook_snapshots = relationship("KalshiOrderbookSnapshot", back_populates="market")
    sharp_odds_snapshots = relationship("SharpBookOddsSnapshot", back_populates="market")
    sharp_limits_snapshots = relationship("SharpBookLimitsSnapshot", back_populates="market")
    derived_metrics = relationship("DerivedMarketMetric", back_populates="market")
    opportunity_scores = relationship("OpportunityScore", back_populates="market")
    kalshi_trades = relationship("KalshiTrade", back_populates="market")
    private_orders = relationship("KalshiPrivateOrder", back_populates="market")
    private_fills = relationship("KalshiPrivateFill", back_populates="market")
    feature_buckets = relationship("MarketFeatureBucket", back_populates="market")
    event_detections = relationship("MarketEventDetection", back_populates="market")


class KalshiOrderbookSnapshot(Base):
    __tablename__ = "kalshi_orderbook_snapshots"
    __table_args__ = (Index("ix_orderbook_market_timestamp", "market_id", "timestamp"),)

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    best_yes_bid = Column(Integer)
    best_yes_ask = Column(Integer)
    best_no_bid = Column(Integer)
    best_no_ask = Column(Integer)
    yes_bid_depth = Column(Integer, default=0, nullable=False)
    yes_ask_depth = Column(Integer, default=0, nullable=False)
    no_bid_depth = Column(Integer, default=0, nullable=False)
    no_ask_depth = Column(Integer, default=0, nullable=False)
    total_depth = Column(Integer, default=0, nullable=False)
    spread = Column(Integer)
    contracts_per_minute = Column(Float)
    volume = Column(Integer)
    yes_book = Column(JSON)
    no_book = Column(JSON)

    market = relationship("Market", back_populates="orderbook_snapshots")


class SharpBookOddsSnapshot(Base):
    __tablename__ = "sharp_book_odds_snapshots"
    __table_args__ = (Index("ix_sharp_odds_market_timestamp", "market_id", "timestamp"),)

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    sportsbook = Column(String(64), index=True, nullable=False)
    side = Column(String(64), index=True, nullable=False)
    american_odds = Column(Integer, nullable=False)
    decimal_odds = Column(Float, nullable=False)
    implied_probability = Column(Float, nullable=False)
    devigged_probability = Column(Float)
    raw_payload = Column(JSON)

    market = relationship("Market", back_populates="sharp_odds_snapshots")


class SharpBookLimitsSnapshot(Base):
    __tablename__ = "sharp_book_limits_snapshots"
    __table_args__ = (Index("ix_sharp_limits_market_timestamp", "market_id", "timestamp"),)

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    sportsbook = Column(String(64), index=True, nullable=False)
    side = Column(String(64), index=True, nullable=False)
    limit_amount = Column(Float)

    market = relationship("Market", back_populates="sharp_limits_snapshots")


class KalshiTrade(Base):
    __tablename__ = "kalshi_trades"
    __table_args__ = (
        UniqueConstraint("trade_id", name="uq_kalshi_trades_trade_id"),
        Index("ix_kalshi_trades_market_timestamp", "market_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    trade_id = Column(String(128), nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    count = Column(Float, nullable=False)
    yes_price = Column(Integer)
    no_price = Column(Integer)
    taker_side = Column(String(32), index=True)
    taker_book_side = Column(String(32), index=True)
    raw_payload = Column(JSON)

    market = relationship("Market", back_populates="kalshi_trades")


class KalshiPrivateOrder(Base):
    __tablename__ = "kalshi_private_orders"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_kalshi_private_orders_order_id"),
        Index("ix_private_orders_market_created", "market_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(String(128), nullable=False)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), index=True, nullable=False)
    side = Column(String(32), index=True)
    action = Column(String(32), index=True)
    price = Column(Integer)
    quantity = Column(Float)
    status = Column(String(32), index=True)
    raw_payload = Column(JSON)

    market = relationship("Market", back_populates="private_orders")


class KalshiPrivateFill(Base):
    __tablename__ = "kalshi_private_fills"
    __table_args__ = (
        UniqueConstraint("fill_id", name="uq_kalshi_private_fills_fill_id"),
        Index("ix_private_fills_market_timestamp", "market_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    fill_id = Column(String(128), nullable=False)
    order_id = Column(String(128), index=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    side = Column(String(32), index=True)
    price = Column(Integer)
    quantity = Column(Float)
    fee = Column(Float)
    raw_payload = Column(JSON)

    market = relationship("Market", back_populates="private_fills")


class MarketFeatureBucket(Base):
    __tablename__ = "market_feature_buckets"
    __table_args__ = (
        UniqueConstraint("market_id", "bucket_start", "bucket_seconds", name="uq_feature_bucket_market_start_size"),
        Index("ix_feature_buckets_market_start", "market_id", "bucket_start"),
        Index("ix_feature_buckets_slice", "sport", "league", "market_type", "bucket_start"),
    )

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    bucket_start = Column(DateTime(timezone=True), index=True, nullable=False)
    bucket_seconds = Column(Integer, default=60, nullable=False)
    sport = Column(String(64), index=True)
    league = Column(String(64), index=True)
    market_type = Column(String(64), index=True)
    time_to_event_minutes = Column(Float)
    day_of_week = Column(Integer, index=True)
    hour_of_day = Column(Integer, index=True)
    best_yes_bid = Column(Integer)
    best_no_bid = Column(Integer)
    consensus_fair_yes = Column(Float)
    consensus_fair_no = Column(Float)
    edge_yes_at_bid = Column(Float)
    edge_no_at_bid = Column(Float)
    volume_delta = Column(Float)
    contracts_per_minute = Column(Float)
    taker_yes_contracts = Column(Float)
    taker_no_contracts = Column(Float)
    one_sided_flow_ratio = Column(Float)
    volume_acceleration = Column(Float)
    spread = Column(Integer)
    total_depth = Column(Integer)
    depth_at_best_yes = Column(Integer)
    depth_at_best_no = Column(Integer)
    orderbook_imbalance = Column(Float)
    ev_at_best_yes_bid = Column(Float)
    ev_at_best_no_bid = Column(Float)
    actual_fill_count = Column(Integer, default=0, nullable=False)
    avg_ev_at_fill = Column(Float)
    source_quality_flags = Column(JSON)

    market = relationship("Market", back_populates="feature_buckets")


class MarketEventDetection(Base):
    __tablename__ = "market_event_detections"
    __table_args__ = (
        Index("ix_market_events_market_started", "market_id", "started_at"),
        Index("ix_market_events_type_started", "event_type", "started_at"),
    )

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String(64), index=True, nullable=False)
    started_at = Column(DateTime(timezone=True), index=True, nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Float)
    side = Column(String(32), index=True)
    magnitude = Column(Float)
    metadata_json = Column(JSON)

    market = relationship("Market", back_populates="event_detections")


class DerivedMarketMetric(Base):
    __tablename__ = "derived_market_metrics"
    __table_args__ = (Index("ix_derived_metrics_market_timestamp", "market_id", "timestamp"),)

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    consensus_fair_probability = Column(Float)
    consensus_fair_price = Column(Integer)
    edge_yes = Column(Float)
    edge_no = Column(Float)
    spread = Column(Integer)
    volatility_score = Column(Float)
    sharp_move_score = Column(Float)
    liquidity_score = Column(Float)
    contracts_per_minute = Column(Float)
    time_to_event_minutes = Column(Float)
    orderbook_imbalance = Column(Float)
    liquidity_stability = Column(Float)
    kalshi_lag_seconds = Column(Float)

    market = relationship("Market", back_populates="derived_metrics")


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"
    __table_args__ = (Index("ix_opportunity_scores_market_timestamp", "market_id", "timestamp"),)

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    queue_positioning_score = Column(Float, default=0, nullable=False)
    stale_opportunity_score = Column(Float, default=0, nullable=False)
    market_making_score = Column(Float, default=0, nullable=False)
    maker_stress_score = Column(Float, default=0, nullable=False)
    notes_json = Column(JSON)

    market = relationship("Market", back_populates="opportunity_scores")


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (UniqueConstraint("job_name", "started_at", name="uq_job_runs_name_started"),)

    id = Column(Integer, primary_key=True)
    job_name = Column(String(128), index=True, nullable=False)
    started_at = Column(DateTime(timezone=True), index=True, nullable=False)
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(32), index=True, nullable=False)
    rows_inserted = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Float)
    error_message = Column(Text)
