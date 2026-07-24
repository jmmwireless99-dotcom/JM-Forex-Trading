from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Tick(BaseModel):
    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp: datetime = Field(default_factory=utcnow)


class Candle(BaseModel):
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    period_seconds: int = 60
    open_time: datetime = Field(default_factory=utcnow)
    timestamp: datetime = Field(default_factory=utcnow)
    is_closed: bool = False


class Signal(BaseModel):
    strategy: str
    symbol: str
    side: Side
    strength: float = 1.0
    reason: str = ""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss_pips: Optional[float] = None
    take_profit_pips: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    expire_at: Optional[datetime] = None
    sweep_price: Optional[float] = None
    timestamp: datetime = Field(default_factory=utcnow)


class OrderRequest(BaseModel):
    symbol: str
    side: Side
    lots: float
    order_type: OrderType = OrderType.MARKET
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy: Optional[str] = None
    comment: str = ""
    # When True (default), fill missing SL/TP from desk defaults at execute time.
    attach_stops: bool = True
    limit_price: Optional[float] = None
    expire_at: Optional[datetime] = None


class Order(BaseModel):
    id: str = Field(default_factory=new_id)
    symbol: str
    side: Side
    lots: float
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    requested_price: Optional[float] = None
    fill_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy: Optional[str] = None
    comment: str = ""
    reject_reason: Optional[str] = None
    limit_price: Optional[float] = None
    expire_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    filled_at: Optional[datetime] = None


class Position(BaseModel):
    id: str = Field(default_factory=new_id)
    symbol: str
    side: Side
    lots: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy: Optional[str] = None
    status: PositionStatus = PositionStatus.OPEN
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None


class AccountSnapshot(BaseModel):
    balance: float
    equity: float
    margin_used: float
    free_margin: float
    open_positions: int
    daily_pnl: float
    currency: str = "USD"
    # Paper desk starting capital (client-selectable deposit for demos)
    deposit: float = 0.0
    paper: bool = True
    timestamp: datetime = Field(default_factory=utcnow)


class EngineStatus(BaseModel):
    running: bool
    mode: str = "paper"
    active_strategy: Optional[str] = None
    symbols: list[str] = Field(default_factory=list)
    ticks_processed: int = 0
    last_tick_at: Optional[datetime] = None
    uptime_seconds: float = 0.0


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class TradeLog(BaseModel):
    """Journal row for every trade attempt / fill / close."""

    id: str = Field(default_factory=new_id)
    ticket: Optional[str] = None  # position id / MT ticket
    symbol: str
    side: Side
    lots: float
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    strategy: Optional[str] = None
    comment: str = ""
    close_reason: Optional[str] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    mode: str = "paper"
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: Optional[datetime] = None
    reject_reason: Optional[str] = None