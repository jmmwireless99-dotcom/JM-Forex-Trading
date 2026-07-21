"""Lightweight repository helpers for persisting scalp desk data."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select

from app.db.models import (
    DbTradeStatus,
    LiquidityZone,
    MarketDataCandle,
    SignalRow,
    SignalSide,
    SignalStatus,
    StrategyRow,
    TradeRow,
    TradeSide,
    ZoneType,
)
from app.db.session import db_enabled, session_scope

log = logging.getLogger(__name__)


def _dec(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def list_strategies(*, active_only: bool = False) -> list[dict]:
    if not db_enabled():
        return []
    with session_scope() as session:
        stmt = select(StrategyRow).order_by(StrategyRow.name)
        if active_only:
            stmt = stmt.where(StrategyRow.is_active.is_(True))
        rows = session.scalars(stmt).all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "timeframe": r.timeframe,
                "parameters": r.parameters,
                "is_active": r.is_active,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


def get_strategy_by_name(name: str) -> StrategyRow | None:
    if not db_enabled():
        return None
    with session_scope() as session:
        row = session.scalar(select(StrategyRow).where(StrategyRow.name == name))
        if row is None:
            return None
        session.expunge(row)
        return row


def upsert_candle(
    *,
    symbol: str,
    timeframe: str,
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 0,
) -> bool:
    if not db_enabled():
        return False
    try:
        with session_scope() as session:
            existing = session.scalar(
                select(MarketDataCandle).where(
                    MarketDataCandle.symbol == symbol.upper(),
                    MarketDataCandle.timeframe == timeframe,
                    MarketDataCandle.timestamp == timestamp,
                )
            )
            if existing:
                existing.open = _dec(open_)
                existing.high = _dec(high)
                existing.low = _dec(low)
                existing.close = _dec(close)
                existing.volume = int(volume)
            else:
                session.add(
                    MarketDataCandle(
                        symbol=symbol.upper(),
                        timeframe=timeframe,
                        timestamp=timestamp,
                        open=_dec(open_),
                        high=_dec(high),
                        low=_dec(low),
                        close=_dec(close),
                        volume=int(volume),
                    )
                )
        return True
    except Exception:  # noqa: BLE001
        log.exception("upsert_candle failed")
        return False


def create_signal(
    *,
    strategy_name: str | None,
    symbol: str,
    signal_type: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    timeframe: str = "M5",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    if not db_enabled():
        return None
    try:
        with session_scope() as session:
            strategy_id = None
            if strategy_name:
                strat = session.scalar(
                    select(StrategyRow).where(StrategyRow.name == strategy_name)
                )
                if strat:
                    strategy_id = strat.id
            risk = None
            risk_amt = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            if risk_amt > 0:
                risk = Decimal(str(round(reward / risk_amt, 3)))
            row = SignalRow(
                strategy_id=strategy_id,
                symbol=symbol.upper(),
                timeframe=timeframe,
                signal_type=SignalSide(signal_type.upper()),
                entry_price=_dec(entry_price),
                stop_loss=_dec(stop_loss),
                take_profit=_dec(take_profit),
                risk_reward_ratio=risk,
                status=SignalStatus.PENDING,
                metadata_=metadata or {},
            )
            session.add(row)
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        log.exception("create_signal failed")
        return None


def create_trade(
    *,
    symbol: str,
    order_type: str,
    lot_size: float,
    open_price: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    signal_id: str | None = None,
    strategy_name: str | None = None,
    ticket: str | None = None,
    mode: str = "paper",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    if not db_enabled():
        return None
    try:
        with session_scope() as session:
            strategy_id = None
            if strategy_name:
                strat = session.scalar(
                    select(StrategyRow).where(StrategyRow.name == strategy_name)
                )
                if strat:
                    strategy_id = strat.id
            sid = uuid.UUID(signal_id) if signal_id else None
            row = TradeRow(
                signal_id=sid,
                strategy_id=strategy_id,
                symbol=symbol.upper(),
                order_type=TradeSide(order_type.upper()),
                lot_size=_dec(lot_size),
                open_price=_dec(open_price),
                stop_loss=_dec(stop_loss),
                take_profit=_dec(take_profit),
                status=DbTradeStatus.OPEN,
                ticket=ticket,
                mode=mode,
                metadata_=metadata or {},
            )
            session.add(row)
            if sid:
                sig = session.get(SignalRow, sid)
                if sig:
                    sig.status = SignalStatus.EXECUTED
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        log.exception("create_trade failed")
        return None


def close_trade(
    *,
    ticket: str | None = None,
    trade_id: str | None = None,
    close_price: float,
    pnl_amount: float | None = None,
    status: str = "CLOSED_MANUAL",
) -> bool:
    if not db_enabled():
        return False
    try:
        with session_scope() as session:
            row: TradeRow | None = None
            if trade_id:
                row = session.get(TradeRow, uuid.UUID(trade_id))
            elif ticket:
                row = session.scalar(select(TradeRow).where(TradeRow.ticket == ticket))
            if row is None:
                return False
            row.close_price = _dec(close_price)
            row.pnl_amount = _dec(pnl_amount)
            if row.open_price is not None and close_price is not None:
                # XAUUSD pip ≈ 0.1
                raw = float(close_price) - float(row.open_price)
                if row.order_type == TradeSide.SELL:
                    raw = -raw
                row.pips_gained = _dec(round(raw / 0.1, 2))
            row.status = DbTradeStatus(status)
            from app.models.domain import utcnow

            row.closed_at = utcnow()
            return True
    except Exception:  # noqa: BLE001
        log.exception("close_trade failed")
        return False


def upsert_zone(
    *,
    symbol: str,
    zone_type: str,
    price_high: float,
    price_low: float,
    timeframe: str = "M5",
    origin_time: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    if not db_enabled():
        return None
    try:
        with session_scope() as session:
            row = LiquidityZone(
                symbol=symbol.upper(),
                timeframe=timeframe,
                zone_type=ZoneType(zone_type),
                price_high=_dec(price_high),
                price_low=_dec(price_low),
                origin_time=origin_time,
                metadata_=metadata or {},
            )
            session.add(row)
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        log.exception("upsert_zone failed")
        return None
