"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=128), nullable=False),
        sa.Column("sport", sa.String(length=64), nullable=True),
        sa.Column("league", sa.String(length=64), nullable=True),
        sa.Column("market_type", sa.String(length=64), nullable=True),
        sa.Column("event_title", sa.Text(), nullable=True),
        sa.Column("event_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("optic_fixture_id", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index(op.f("ix_markets_event_start_time"), "markets", ["event_start_time"], unique=False)
    op.create_index(op.f("ix_markets_league"), "markets", ["league"], unique=False)
    op.create_index(op.f("ix_markets_market_type"), "markets", ["market_type"], unique=False)
    op.create_index(op.f("ix_markets_optic_fixture_id"), "markets", ["optic_fixture_id"], unique=False)
    op.create_index(op.f("ix_markets_sport"), "markets", ["sport"], unique=False)
    op.create_index(op.f("ix_markets_status"), "markets", ["status"], unique=False)
    op.create_index(op.f("ix_markets_ticker"), "markets", ["ticker"], unique=False)

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_name", "started_at", name="uq_job_runs_name_started"),
    )
    op.create_index(op.f("ix_job_runs_job_name"), "job_runs", ["job_name"], unique=False)
    op.create_index(op.f("ix_job_runs_started_at"), "job_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_job_runs_status"), "job_runs", ["status"], unique=False)

    op.create_table(
        "kalshi_orderbook_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("best_yes_bid", sa.Integer(), nullable=True),
        sa.Column("best_yes_ask", sa.Integer(), nullable=True),
        sa.Column("best_no_bid", sa.Integer(), nullable=True),
        sa.Column("best_no_ask", sa.Integer(), nullable=True),
        sa.Column("yes_bid_depth", sa.Integer(), nullable=False),
        sa.Column("yes_ask_depth", sa.Integer(), nullable=False),
        sa.Column("no_bid_depth", sa.Integer(), nullable=False),
        sa.Column("no_ask_depth", sa.Integer(), nullable=False),
        sa.Column("total_depth", sa.Integer(), nullable=False),
        sa.Column("spread", sa.Integer(), nullable=True),
        sa.Column("contracts_per_minute", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("yes_book", sa.JSON(), nullable=True),
        sa.Column("no_book", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orderbook_market_timestamp", "kalshi_orderbook_snapshots", ["market_id", "timestamp"])
    op.create_index(op.f("ix_kalshi_orderbook_snapshots_market_id"), "kalshi_orderbook_snapshots", ["market_id"])
    op.create_index(op.f("ix_kalshi_orderbook_snapshots_timestamp"), "kalshi_orderbook_snapshots", ["timestamp"])

    op.create_table(
        "sharp_book_odds_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sportsbook", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=64), nullable=False),
        sa.Column("american_odds", sa.Integer(), nullable=False),
        sa.Column("decimal_odds", sa.Float(), nullable=False),
        sa.Column("implied_probability", sa.Float(), nullable=False),
        sa.Column("devigged_probability", sa.Float(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sharp_odds_market_timestamp", "sharp_book_odds_snapshots", ["market_id", "timestamp"])
    op.create_index(op.f("ix_sharp_book_odds_snapshots_market_id"), "sharp_book_odds_snapshots", ["market_id"])
    op.create_index(op.f("ix_sharp_book_odds_snapshots_side"), "sharp_book_odds_snapshots", ["side"])
    op.create_index(op.f("ix_sharp_book_odds_snapshots_sportsbook"), "sharp_book_odds_snapshots", ["sportsbook"])
    op.create_index(op.f("ix_sharp_book_odds_snapshots_timestamp"), "sharp_book_odds_snapshots", ["timestamp"])

    op.create_table(
        "sharp_book_limits_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sportsbook", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=64), nullable=False),
        sa.Column("limit_amount", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sharp_limits_market_timestamp", "sharp_book_limits_snapshots", ["market_id", "timestamp"])
    op.create_index(op.f("ix_sharp_book_limits_snapshots_market_id"), "sharp_book_limits_snapshots", ["market_id"])
    op.create_index(op.f("ix_sharp_book_limits_snapshots_side"), "sharp_book_limits_snapshots", ["side"])
    op.create_index(op.f("ix_sharp_book_limits_snapshots_sportsbook"), "sharp_book_limits_snapshots", ["sportsbook"])
    op.create_index(op.f("ix_sharp_book_limits_snapshots_timestamp"), "sharp_book_limits_snapshots", ["timestamp"])

    op.create_table(
        "derived_market_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consensus_fair_probability", sa.Float(), nullable=True),
        sa.Column("consensus_fair_price", sa.Integer(), nullable=True),
        sa.Column("edge_yes", sa.Float(), nullable=True),
        sa.Column("edge_no", sa.Float(), nullable=True),
        sa.Column("spread", sa.Integer(), nullable=True),
        sa.Column("volatility_score", sa.Float(), nullable=True),
        sa.Column("sharp_move_score", sa.Float(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.Column("contracts_per_minute", sa.Float(), nullable=True),
        sa.Column("time_to_event_minutes", sa.Float(), nullable=True),
        sa.Column("orderbook_imbalance", sa.Float(), nullable=True),
        sa.Column("liquidity_stability", sa.Float(), nullable=True),
        sa.Column("kalshi_lag_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_derived_metrics_market_timestamp", "derived_market_metrics", ["market_id", "timestamp"])
    op.create_index(op.f("ix_derived_market_metrics_market_id"), "derived_market_metrics", ["market_id"])
    op.create_index(op.f("ix_derived_market_metrics_timestamp"), "derived_market_metrics", ["timestamp"])

    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_positioning_score", sa.Float(), nullable=False),
        sa.Column("stale_opportunity_score", sa.Float(), nullable=False),
        sa.Column("market_making_score", sa.Float(), nullable=False),
        sa.Column("maker_stress_score", sa.Float(), nullable=False),
        sa.Column("notes_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_scores_market_timestamp", "opportunity_scores", ["market_id", "timestamp"])
    op.create_index(op.f("ix_opportunity_scores_market_id"), "opportunity_scores", ["market_id"])
    op.create_index(op.f("ix_opportunity_scores_timestamp"), "opportunity_scores", ["timestamp"])


def downgrade() -> None:
    op.drop_table("opportunity_scores")
    op.drop_table("derived_market_metrics")
    op.drop_table("sharp_book_limits_snapshots")
    op.drop_table("sharp_book_odds_snapshots")
    op.drop_table("kalshi_orderbook_snapshots")
    op.drop_table("job_runs")
    op.drop_table("markets")
