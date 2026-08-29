"""Keep DDDC3D JM FX trade logs aligned with live MT5 bridge positions."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.models.domain import (
    Order,
    OrderStatus,
    Position,
    PositionStatus,
    Side,
    Tick,
    TradeLog,
    TradeStatus,
    utcnow,
)
from app.paper_accounts.registry import _exit_from_pnl, _pnl_at_price

if TYPE_CHECKING:
    from app.brokers.mt4_bridge import MT4FileBridge
    from app.engine.trade_journal import TradeJournal


def parse_mt5_ticket(order: Order) -> str | None:
    comment = (order.comment or "").strip()
    if comment.startswith("mt5:"):
        ticket = comment.split(":", 1)[1].strip()
        return ticket or None
    return None


def wait_mt_position(
    bridge: MT4FileBridge,
    ticket: str,
    *,
    timeout: float = 5.0,
    poll: float = 0.12,
) -> Position | None:
    deadline = time.time() + timeout
    want = str(ticket)
    while time.time() < deadline:
        for pos in bridge.open_positions():
            if str(pos.id) == want:
                return pos
        time.sleep(poll)
    return None


def _mark_price(tick: Tick | None, side: Side) -> float | None:
    if tick is None:
        return None
    return tick.bid if side == Side.BUY else tick.ask


def _close_row_from_mt5(
    row: TradeLog,
    *,
    tick: Tick | None,
    reason: str = "mt5_close",
) -> Position:
    exit_price = _mark_price(tick, row.side)
    pnl = float(row.unrealized_pnl or 0.0)
    if pnl == 0.0 and row.entry is not None and exit_price is not None:
        pnl = _pnl_at_price(
            entry=float(row.entry),
            side=row.side.value,
            lots=float(row.lots),
            symbol=row.symbol,
            price=exit_price,
        )
    if exit_price is None and row.entry is not None and pnl != 0.0:
        exit_price = _exit_from_pnl(
            entry=float(row.entry),
            side=row.side.value,
            lots=float(row.lots),
            symbol=row.symbol,
            pnl=pnl,
        )
    return Position(
        id=str(row.ticket or row.id),
        symbol=row.symbol,
        side=row.side,
        lots=row.lots,
        entry_price=float(row.entry or 0.0),
        stop_loss=row.stop_loss,
        take_profit=row.take_profit,
        strategy=row.strategy,
        status=PositionStatus.CLOSED,
        unrealized_pnl=0.0,
        realized_pnl=round(pnl, 2),
        close_price=exit_price,
        close_reason=reason,
        opened_at=row.opened_at,
        closed_at=utcnow(),
    )


def sync_journal_with_mt5(
    journal: TradeJournal,
    positions: list[Position],
    *,
    tick: Tick | None = None,
    mode: str = "mt5",
) -> dict[str, int | list[str]]:
    """Mirror MT5 open/close state into the JM FX trade journal."""
    mt_by_ticket = {str(p.id): p for p in positions}
    open_rows = [t for t in journal._trades if t.status == TradeStatus.OPEN]
    closed_ids: list[str] = []
    updated = 0
    opened = 0

    for row in open_rows:
        ticket = str(row.ticket or "")
        mt_pos = mt_by_ticket.get(ticket)
        if mt_pos is None:
            parsed = parse_mt5_ticket(
                Order(
                    symbol=row.symbol,
                    side=row.side,
                    lots=row.lots,
                    comment=row.comment or "",
                    status=OrderStatus.FILLED,
                )
            )
            if parsed:
                mt_pos = mt_by_ticket.get(parsed)
                if mt_pos is not None:
                    journal._by_ticket.pop(ticket, None)
                    row.ticket = parsed
                    journal._by_ticket[parsed] = row

        if mt_pos is None:
            closed = _close_row_from_mt5(row, tick=tick)
            journal.record_close(closed)
            closed_ids.append(str(row.ticket or row.id))
            continue

        row.ticket = str(mt_pos.id)
        row.entry = mt_pos.entry_price
        row.stop_loss = mt_pos.stop_loss
        row.take_profit = mt_pos.take_profit
        row.lots = mt_pos.lots
        row.unrealized_pnl = mt_pos.unrealized_pnl
        row.mode = mode
        if not (row.comment or "").startswith("mt5:"):
            row.comment = f"mt5:{mt_pos.id}"
        journal._by_ticket[str(mt_pos.id)] = row
        mt_by_ticket.pop(str(mt_pos.id), None)
        updated += 1

    for mt_pos in mt_by_ticket.values():
        journal.record_open_position(
            mt_pos.model_copy(update={"strategy": mt_pos.strategy or "MT5_MANUAL"}),
            mode=mode,
        )
        opened += 1

    return {"closed": len(closed_ids), "updated": updated, "opened": opened, "closed_ids": closed_ids}


def journal_row_from_mt5_fill(
    order: Order,
    position: Position,
    *,
    mode: str = "mt5",
) -> TradeLog:
    ticket = str(position.id)
    return TradeLog(
        ticket=ticket,
        symbol=position.symbol,
        side=position.side,
        lots=position.lots,
        entry=position.entry_price,
        stop_loss=position.stop_loss or order.stop_loss,
        take_profit=position.take_profit or order.take_profit,
        status=TradeStatus.OPEN,
        strategy=order.strategy or position.strategy,
        comment=f"mt5:{ticket}",
        mode=mode,
        opened_at=order.filled_at or utcnow(),
        unrealized_pnl=position.unrealized_pnl,
    )
