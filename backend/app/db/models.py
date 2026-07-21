"""SQLAlchemy ORM models for the XAUUSD scalping desk."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ZoneType(str, enum.Enum):
    ASIAN_HIGH = "ASIAN_HIGH"
    ASIAN_LOW = "ASIAN_LOW"
    PDH = "PDH"
    PDL = "PDL"
    SUPPLY_ZONE = "SUPPLY_ZONE"
    DEMAND_ZONE = "DEMAND_ZONE"
    FVG = "FVG"
    ORDER_BLOCK = "ORDER_BLOCK"


class SignalSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalStatus(str, enum.Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TradeSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class DbTradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_MANUAL = "CLOSED_MANUAL"
    REJECTED = "REJECTED"


class StrategyRow(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="M5")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    signals: Mapped[list["SignalRow"]] = relationship(back_populates="strategy")
    trades: Mapped[list["TradeRow"]] = relationship(back_populates="strategy")


class MarketDataCandle(Base):
    __tablename__ = "market_data_candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candles_symbol_tf_ts"),
        Index("ix_candles_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class LiquidityZone(Base):
    __tablename__ = "liquidity_zones_and_fvgs"
    __table_args__ = (
        Index("ix_zones_symbol_type", "symbol", "zone_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, default="XAUUSD")
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="M5")
    zone_type: Mapped[ZoneType] = mapped_column(
        Enum(ZoneType, name="zone_type", native_enum=True, create_constraint=False),
        nullable=False,
    )
    price_high: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    price_low: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    is_swept: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    swept_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_mitigated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    origin_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SignalRow(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_status", "status"),
        Index("ix_signals_symbol_created", "symbol", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategies.id", ondelete="SET NULL")
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, default="XAUUSD")
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="M5")
    signal_type: Mapped[SignalSide] = mapped_column(
        Enum(SignalSide, name="signal_side", native_enum=True, create_constraint=False),
        nullable=False,
    )
    entry_price: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    stop_loss: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    take_profit: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Numeric(8, 3))
    status: Mapped[SignalStatus] = mapped_column(
        Enum(
            SignalStatus,
            name="signal_status",
            native_enum=True,
            create_constraint=False,
        ),
        nullable=False,
        default=SignalStatus.PENDING,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    strategy: Mapped[Optional[StrategyRow]] = relationship(back_populates="signals")
    trades: Mapped[list["TradeRow"]] = relationship(back_populates="signal")


class TradeRow(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_status", "status"),
        Index("ix_trades_symbol_opened", "symbol", "opened_at"),
        Index("ix_trades_ticket", "ticket"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL")
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategies.id", ondelete="SET NULL")
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, default="XAUUSD")
    order_type: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, name="trade_side", native_enum=True, create_constraint=False),
        nullable=False,
    )
    lot_size: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    open_price: Mapped[float] = mapped_column(Numeric(14, 5), nullable=False)
    close_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 5))
    stop_loss: Mapped[Optional[float]] = mapped_column(Numeric(14, 5))
    take_profit: Mapped[Optional[float]] = mapped_column(Numeric(14, 5))
    pnl_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    pips_gained: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    status: Mapped[DbTradeStatus] = mapped_column(
        Enum(
            DbTradeStatus,
            name="trade_status",
            native_enum=True,
            create_constraint=False,
        ),
        nullable=False,
        default=DbTradeStatus.OPEN,
    )
    ticket: Mapped[Optional[str]] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="paper")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    signal: Mapped[Optional[SignalRow]] = relationship(back_populates="trades")
    strategy: Mapped[Optional[StrategyRow]] = relationship(back_populates="trades")
