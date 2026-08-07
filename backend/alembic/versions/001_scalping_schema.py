"""Initial XAUUSD scalping schema

Revision ID: 001_scalping_schema
Revises:
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_scalping_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

zone_type = postgresql.ENUM(
    "ASIAN_HIGH",
    "ASIAN_LOW",
    "PDH",
    "PDL",
    "SUPPLY_ZONE",
    "DEMAND_ZONE",
    "FVG",
    "ORDER_BLOCK",
    name="zone_type",
    create_type=False,
)
signal_side = postgresql.ENUM("BUY", "SELL", name="signal_side", create_type=False)
signal_status = postgresql.ENUM(
    "PENDING", "EXECUTED", "CANCELLED", "EXPIRED", name="signal_status", create_type=False
)
trade_side = postgresql.ENUM("BUY", "SELL", name="trade_side", create_type=False)
trade_status = postgresql.ENUM(
    "OPEN",
    "CLOSED_TP",
    "CLOSED_SL",
    "CLOSED_MANUAL",
    "REJECTED",
    name="trade_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_obj in (zone_type, signal_side, signal_status, trade_side, trade_status):
        enum_obj.create(bind, checkfirst=True)

    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("timeframe", sa.String(8), nullable=False, server_default="M5"),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_strategies_active", "strategies", ["is_active"])

    op.create_table(
        "market_data_candles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(14, 5), nullable=False),
        sa.Column("high", sa.Numeric(14, 5), nullable=False),
        sa.Column("low", sa.Numeric(14, 5), nullable=False),
        sa.Column("close", sa.Numeric(14, 5), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "symbol", "timeframe", "timestamp", name="uq_candles_symbol_tf_ts"
        ),
    )
    op.create_index(
        "ix_candles_symbol_tf_ts",
        "market_data_candles",
        ["symbol", "timeframe", "timestamp"],
    )

    op.create_table(
        "liquidity_zones_and_fvgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False, server_default="XAUUSD"),
        sa.Column("timeframe", sa.String(8), nullable=False, server_default="M5"),
        sa.Column("zone_type", zone_type, nullable=False),
        sa.Column("price_high", sa.Numeric(14, 5), nullable=False),
        sa.Column("price_low", sa.Numeric(14, 5), nullable=False),
        sa.Column("is_swept", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("swept_at", sa.DateTime(timezone=True)),
        sa.Column(
            "is_mitigated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("mitigated_at", sa.DateTime(timezone=True)),
        sa.Column("origin_time", sa.DateTime(timezone=True)),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_zones_symbol_type", "liquidity_zones_and_fvgs", ["symbol", "zone_type"]
    )

    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
        ),
        sa.Column("symbol", sa.String(16), nullable=False, server_default="XAUUSD"),
        sa.Column("timeframe", sa.String(8), nullable=False, server_default="M5"),
        sa.Column("signal_type", signal_side, nullable=False),
        sa.Column("entry_price", sa.Numeric(14, 5), nullable=False),
        sa.Column("stop_loss", sa.Numeric(14, 5), nullable=False),
        sa.Column("take_profit", sa.Numeric(14, 5), nullable=False),
        sa.Column("risk_reward_ratio", sa.Numeric(8, 3)),
        sa.Column(
            "status",
            signal_status,
            nullable=False,
            server_default="PENDING",
        ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_signals_strategy", "signals", ["strategy_id"])
    op.create_index("ix_signals_status", "signals", ["status"])
    op.create_index("ix_signals_symbol_created", "signals", ["symbol", "created_at"])

    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
        ),
        sa.Column("symbol", sa.String(16), nullable=False, server_default="XAUUSD"),
        sa.Column("order_type", trade_side, nullable=False),
        sa.Column("lot_size", sa.Numeric(10, 4), nullable=False),
        sa.Column("open_price", sa.Numeric(14, 5), nullable=False),
        sa.Column("close_price", sa.Numeric(14, 5)),
        sa.Column("stop_loss", sa.Numeric(14, 5)),
        sa.Column("take_profit", sa.Numeric(14, 5)),
        sa.Column("pnl_amount", sa.Numeric(14, 4)),
        sa.Column("pips_gained", sa.Numeric(12, 2)),
        sa.Column(
            "status",
            trade_status,
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("ticket", sa.String(64)),
        sa.Column("mode", sa.String(16), nullable=False, server_default="paper"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_trades_status", "trades", ["status"])
    op.create_index("ix_trades_symbol_opened", "trades", ["symbol", "opened_at"])
    op.create_index("ix_trades_signal", "trades", ["signal_id"])
    op.create_index("ix_trades_ticket", "trades", ["ticket"])


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("signals")
    op.drop_table("liquidity_zones_and_fvgs")
    op.drop_table("market_data_candles")
    op.drop_table("strategies")
    bind = op.get_bind()
    for enum_obj in (trade_status, trade_side, signal_status, signal_side, zone_type):
        enum_obj.drop(bind, checkfirst=True)
