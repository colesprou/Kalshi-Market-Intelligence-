"""bi data foundation

Revision ID: 0002_bi_data_foundation
Revises: 0001_initial_schema
Create Date: 2026-05-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_bi_data_foundation"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kalshi_trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Float(), nullable=False),
        sa.Column("yes_price", sa.Integer(), nullable=True),
        sa.Column("no_price", sa.Integer(), nullable=True),
        sa.Column("taker_side", sa.String(length=32), nullable=True),
        sa.Column("taker_book_side", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_id", name="uq_kalshi_trades_trade_id"),
    )
    op.create_index("ix_kalshi_trades_market_timestamp", "kalshi_trades", ["market_id", "timestamp"])
    op.create_index(op.f("ix_kalshi_trades_market_id"), "kalshi_trades", ["market_id"])
    op.create_index(op.f("ix_kalshi_trades_taker_book_side"), "kalshi_trades", ["taker_book_side"])
    op.create_index(op.f("ix_kalshi_trades_taker_side"), "kalshi_trades", ["taker_side"])
    op.create_index(op.f("ix_kalshi_trades_timestamp"), "kalshi_trades", ["timestamp"])

    op.create_table(
        "kalshi_private_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_kalshi_private_orders_order_id"),
    )
    op.create_index("ix_private_orders_market_created", "kalshi_private_orders", ["market_id", "created_at"])
    op.create_index(op.f("ix_kalshi_private_orders_action"), "kalshi_private_orders", ["action"])
    op.create_index(op.f("ix_kalshi_private_orders_created_at"), "kalshi_private_orders", ["created_at"])
    op.create_index(op.f("ix_kalshi_private_orders_market_id"), "kalshi_private_orders", ["market_id"])
    op.create_index(op.f("ix_kalshi_private_orders_side"), "kalshi_private_orders", ["side"])
    op.create_index(op.f("ix_kalshi_private_orders_status"), "kalshi_private_orders", ["status"])

    op.create_table(
        "kalshi_private_fills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fill_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("fee", sa.Float(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fill_id", name="uq_kalshi_private_fills_fill_id"),
    )
    op.create_index("ix_private_fills_market_timestamp", "kalshi_private_fills", ["market_id", "timestamp"])
    op.create_index(op.f("ix_kalshi_private_fills_market_id"), "kalshi_private_fills", ["market_id"])
    op.create_index(op.f("ix_kalshi_private_fills_order_id"), "kalshi_private_fills", ["order_id"])
    op.create_index(op.f("ix_kalshi_private_fills_side"), "kalshi_private_fills", ["side"])
    op.create_index(op.f("ix_kalshi_private_fills_timestamp"), "kalshi_private_fills", ["timestamp"])

    op.create_table(
        "market_feature_buckets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_seconds", sa.Integer(), nullable=False),
        sa.Column("sport", sa.String(length=64), nullable=True),
        sa.Column("league", sa.String(length=64), nullable=True),
        sa.Column("market_type", sa.String(length=64), nullable=True),
        sa.Column("time_to_event_minutes", sa.Float(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("hour_of_day", sa.Integer(), nullable=True),
        sa.Column("best_yes_bid", sa.Integer(), nullable=True),
        sa.Column("best_no_bid", sa.Integer(), nullable=True),
        sa.Column("consensus_fair_yes", sa.Float(), nullable=True),
        sa.Column("consensus_fair_no", sa.Float(), nullable=True),
        sa.Column("edge_yes_at_bid", sa.Float(), nullable=True),
        sa.Column("edge_no_at_bid", sa.Float(), nullable=True),
        sa.Column("volume_delta", sa.Float(), nullable=True),
        sa.Column("contracts_per_minute", sa.Float(), nullable=True),
        sa.Column("taker_yes_contracts", sa.Float(), nullable=True),
        sa.Column("taker_no_contracts", sa.Float(), nullable=True),
        sa.Column("one_sided_flow_ratio", sa.Float(), nullable=True),
        sa.Column("volume_acceleration", sa.Float(), nullable=True),
        sa.Column("spread", sa.Integer(), nullable=True),
        sa.Column("total_depth", sa.Integer(), nullable=True),
        sa.Column("depth_at_best_yes", sa.Integer(), nullable=True),
        sa.Column("depth_at_best_no", sa.Integer(), nullable=True),
        sa.Column("orderbook_imbalance", sa.Float(), nullable=True),
        sa.Column("ev_at_best_yes_bid", sa.Float(), nullable=True),
        sa.Column("ev_at_best_no_bid", sa.Float(), nullable=True),
        sa.Column("actual_fill_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_ev_at_fill", sa.Float(), nullable=True),
        sa.Column("source_quality_flags", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "bucket_start", "bucket_seconds", name="uq_feature_bucket_market_start_size"),
    )
    op.create_index("ix_feature_buckets_market_start", "market_feature_buckets", ["market_id", "bucket_start"])
    op.create_index("ix_feature_buckets_slice", "market_feature_buckets", ["sport", "league", "market_type", "bucket_start"])
    op.create_index(op.f("ix_market_feature_buckets_bucket_start"), "market_feature_buckets", ["bucket_start"])
    op.create_index(op.f("ix_market_feature_buckets_day_of_week"), "market_feature_buckets", ["day_of_week"])
    op.create_index(op.f("ix_market_feature_buckets_hour_of_day"), "market_feature_buckets", ["hour_of_day"])
    op.create_index(op.f("ix_market_feature_buckets_league"), "market_feature_buckets", ["league"])
    op.create_index(op.f("ix_market_feature_buckets_market_id"), "market_feature_buckets", ["market_id"])
    op.create_index(op.f("ix_market_feature_buckets_market_type"), "market_feature_buckets", ["market_type"])
    op.create_index(op.f("ix_market_feature_buckets_sport"), "market_feature_buckets", ["sport"])

    op.create_table(
        "market_event_detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_events_market_started", "market_event_detections", ["market_id", "started_at"])
    op.create_index("ix_market_events_type_started", "market_event_detections", ["event_type", "started_at"])
    op.create_index(op.f("ix_market_event_detections_event_type"), "market_event_detections", ["event_type"])
    op.create_index(op.f("ix_market_event_detections_market_id"), "market_event_detections", ["market_id"])
    op.create_index(op.f("ix_market_event_detections_side"), "market_event_detections", ["side"])
    op.create_index(op.f("ix_market_event_detections_started_at"), "market_event_detections", ["started_at"])


def downgrade() -> None:
    op.drop_table("market_event_detections")
    op.drop_table("market_feature_buckets")
    op.drop_table("kalshi_private_fills")
    op.drop_table("kalshi_private_orders")
    op.drop_table("kalshi_trades")
