"""live market signals

Revision ID: 0003_live_market_signals
Revises: 0002_bi_data_foundation
Create Date: 2026-05-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_live_market_signals"
down_revision = "0002_bi_data_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_market_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("contracts_last_5s", sa.Float(), nullable=True),
        sa.Column("contracts_last_10s", sa.Float(), nullable=True),
        sa.Column("contracts_last_30s", sa.Float(), nullable=True),
        sa.Column("contracts_last_60s", sa.Float(), nullable=True),
        sa.Column("trailing_cpm_5m", sa.Float(), nullable=True),
        sa.Column("expected_contracts_10s", sa.Float(), nullable=True),
        sa.Column("flow_spike_ratio", sa.Float(), nullable=True),
        sa.Column("taker_side", sa.String(length=32), nullable=True),
        sa.Column("taker_side_imbalance", sa.Float(), nullable=True),
        sa.Column("taker_yes_last_10s", sa.Float(), nullable=True),
        sa.Column("taker_no_last_10s", sa.Float(), nullable=True),
        sa.Column("best_yes_bid", sa.Integer(), nullable=True),
        sa.Column("best_yes_ask", sa.Integer(), nullable=True),
        sa.Column("best_no_bid", sa.Integer(), nullable=True),
        sa.Column("best_no_ask", sa.Integer(), nullable=True),
        sa.Column("spread", sa.Integer(), nullable=True),
        sa.Column("total_depth", sa.Integer(), nullable=True),
        sa.Column("depth_change_after_spike", sa.Integer(), nullable=True),
        sa.Column("spread_change_after_spike", sa.Integer(), nullable=True),
        sa.Column("kalshi_price_change_after_spike", sa.Integer(), nullable=True),
        sa.Column("signal_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_live_signals_market_timestamp", "live_market_signals", ["market_id", "timestamp"])
    op.create_index("ix_live_signals_type_timestamp", "live_market_signals", ["signal_type", "timestamp"])
    op.create_index(op.f("ix_live_market_signals_market_id"), "live_market_signals", ["market_id"])
    op.create_index(op.f("ix_live_market_signals_signal_type"), "live_market_signals", ["signal_type"])
    op.create_index(op.f("ix_live_market_signals_taker_side"), "live_market_signals", ["taker_side"])
    op.create_index(op.f("ix_live_market_signals_timestamp"), "live_market_signals", ["timestamp"])


def downgrade() -> None:
    op.drop_table("live_market_signals")
