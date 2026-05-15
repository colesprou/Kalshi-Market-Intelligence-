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
