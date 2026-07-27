"""Add london_session_ranges and london_signals

Revision ID: 002_london_judas
Revises: 001_scalping_schema
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_london_judas"
down_revision: Union[str, None] = "001_scalping_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

london_signal_status = postgresql.ENUM(
    "PENDING",
    "EXECUTED",
    "INVALIDATED",
    "CLOSED_TP",
    "CLOSED_SL",
    "CANCELLED",
    name="london_signal_status",
    create_type=False,
)
signal_side = postgresql.ENUM("BUY", "SELL", name="signal_side", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    london_signal_status.create(bind, checkfirst=True)

    op.create_table(
        "london_session_ranges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("asian_high", sa.Numeric(14, 5), nullable=False),
        sa.Column("asian_low", sa.Numeric(14, 5), nullable=False),
        sa.Column("asian_range_pips", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "is_swept_high", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_swept_low", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("date", name="uq_london_session_date"),
    )

    op.create_table(
        "london_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("london_session_ranges.id", ondelete="SET NULL"),
        ),
        sa.Column("signal_type", signal_side, nullable=False),
        sa.Column("sweep_price", sa.Numeric(14, 5), nullable=False),
        sa.Column("entry_price", sa.Numeric(14, 5), nullable=False),
        sa.Column("stop_loss", sa.Numeric(14, 5), nullable=False),
        sa.Column("take_profit", sa.Numeric(14, 5), nullable=False),
        sa.Column("risk_reward_ratio", sa.Numeric(8, 3)),
        sa.Column(
            "status",
            london_signal_status,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("execution_timestamp", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_london_signals_status", "london_signals", ["status"])


def downgrade() -> None:
    op.drop_table("london_signals")
    op.drop_table("london_session_ranges")
    bind = op.get_bind()
    london_signal_status.drop(bind, checkfirst=True)
