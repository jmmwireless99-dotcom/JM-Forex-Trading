from __future__ import annotations

from collections import deque
from copy import deepcopy

from app.models.domain import (
    Order,
    OrderStatus,
    Position,
    PositionStatus,
    TradeLog,
    TradeStatus,
    utcnow,
)


class TradeJournal:
    """In-memory trade log: entry / SL / TP / exit / PnL for the desk UI."""

    def __init__(self, maxlen: int = 500) -> None:
        self._trades: deque[TradeLog] = deque(maxlen=maxlen)
        self._by_ticket: dict[str, TradeLog] = {}

    def record_order(self, order: Order, *, mode: str = "paper") -> TradeLog:
        if order.status == OrderStatus.REJECTED:
            row = TradeLog(
                ticket=order.id,
                symbol=order.symbol,
                side=order.side,
                lots=order.lots,
                entry=order.fill_price or order.requested_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                status=TradeStatus.REJECTED,
                strategy=order.strategy,
                comment=order.comment,
                mode=mode,
                opened_at=order.created_at or utcnow(),
                closed_at=utcnow(),
                reject_reason=order.reject_reason,
            )
            self._trades.appendleft(row)
            return row

        row = TradeLog(
            ticket=order.id,
            symbol=order.symbol,
            side=order.side,
            lots=order.lots,
            entry=order.fill_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            status=TradeStatus.OPEN,
            strategy=order.strategy,
            comment=order.comment,
            mode=mode,
            opened_at=order.filled_at or order.created_at or utcnow(),
        )
        self._trades.appendleft(row)
        if order.id:
            self._by_ticket[order.id] = row
        return row

    def record_open_position(self, position: Position, *, mode: str = "paper") -> TradeLog:
        existing = self._by_ticket.get(position.id)
        if existing and existing.status == TradeStatus.OPEN:
            existing.entry = position.entry_price
            existing.stop_loss = position.stop_loss
            existing.take_profit = position.take_profit
            existing.lots = position.lots
            existing.unrealized_pnl = position.unrealized_pnl
            existing.strategy = position.strategy or existing.strategy
            return existing

        row = TradeLog(
            ticket=position.id,
            symbol=position.symbol,
            side=position.side,
            lots=position.lots,
            entry=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            status=TradeStatus.OPEN,
            strategy=position.strategy,
            mode=mode,
            opened_at=position.opened_at or utcnow(),
            unrealized_pnl=position.unrealized_pnl,
        )
        self._trades.appendleft(row)
        self._by_ticket[position.id] = row
        return row

    def update_open_pnl(self, positions: list[Position]) -> None:
        for position in positions:
            row = self._by_ticket.get(position.id)
            if row and row.status == TradeStatus.OPEN:
                row.unrealized_pnl = position.unrealized_pnl
                row.stop_loss = position.stop_loss
                row.take_profit = position.take_profit

    def record_close(self, position: Position) -> TradeLog | None:
        row = self._by_ticket.get(position.id)
        if row is None:
            row = TradeLog(
                ticket=position.id,
                symbol=position.symbol,
                side=position.side,
                lots=position.lots,
                entry=position.entry_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                strategy=position.strategy,
                opened_at=position.opened_at or utcnow(),
            )
            self._trades.appendleft(row)
            self._by_ticket[position.id] = row

        row.status = TradeStatus.CLOSED
        row.exit = position.close_price
        row.realized_pnl = position.realized_pnl
        row.unrealized_pnl = 0.0
        row.close_reason = position.close_reason
        row.closed_at = position.closed_at or utcnow()
        row.stop_loss = position.stop_loss
        row.take_profit = position.take_profit
        return row

    def list(self, limit: int = 100, *, include_rejected: bool = True) -> list[TradeLog]:
        rows = list(self._trades)
        if not include_rejected:
            rows = [r for r in rows if r.status != TradeStatus.REJECTED]
        return [deepcopy(r) for r in rows[:limit]]

    def summary(self) -> dict:
        closed = [t for t in self._trades if t.status == TradeStatus.CLOSED]
        opens = [t for t in self._trades if t.status == TradeStatus.OPEN]
        wins = [t for t in closed if t.realized_pnl > 0]
        losses = [t for t in closed if t.realized_pnl < 0]
        net = sum(t.realized_pnl for t in closed)
        return {
            "total": len(self._trades),
            "open": len(opens),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "rejected": sum(1 for t in self._trades if t.status == TradeStatus.REJECTED),
            "net_pnl": round(net, 2),
            "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        }

    def clear(self) -> None:
        """Wipe in-memory trade log (used when paper deposit is reset)."""
        self._trades.clear()
        self._by_ticket.clear()
