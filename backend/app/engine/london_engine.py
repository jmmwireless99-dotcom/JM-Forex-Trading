"""London session helpers — Asian range snapshot + pending limit kill switch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.models.domain import Candle, Order, OrderStatus
from app.strategies.london_session import (
    calculate_asian_range,
    is_london_entry_window,
    is_past_pending_kill,
)


@dataclass
class LondonDeskSnapshot:
    in_entry_window: bool
    past_kill: bool
    asian_range: dict[str, Any] | None
    last_block: str | None
    checklist: list[dict]
    pending_note: str


class LondonEngine:
    """Session board for London hours (Judas strategy removed — stand aside)."""

    def snapshot(self, bars_m5: list[Candle], ts: datetime) -> LondonDeskSnapshot:
        asian = calculate_asian_range(bars_m5, as_of=ts)
        in_window = is_london_entry_window(ts)
        block = (
            "London session — stand aside (Judas removed)"
            if in_window
            else "Outside London entry window (07:00–11:00 UTC)"
        )
        return LondonDeskSnapshot(
            in_entry_window=in_window,
            past_kill=is_past_pending_kill(ts),
            asian_range=(
                {
                    "date": asian.session_date.isoformat(),
                    "high": asian.high,
                    "low": asian.low,
                    "range_pips": asian.range_pips,
                    "bar_count": asian.bar_count,
                }
                if asian
                else None
            ),
            last_block=block,
            checklist=[],
            pending_note="Unfilled LIMIT orders auto-cancel at 12:00 UTC",
        )

    def as_dict(self, bars_m5: list[Candle], ts: datetime) -> dict:
        return asdict(self.snapshot(bars_m5, ts))


def cancel_expired_pending(orders: list[Order], ts: datetime) -> list[Order]:
    """Mark PENDING limit orders CANCELLED at/after 12:00 UTC kill switch."""
    cancelled: list[Order] = []
    kill = is_past_pending_kill(ts)
    for order in orders:
        if order.status != OrderStatus.PENDING:
            continue
        if order.order_type.value != "LIMIT":
            continue
        expired = order.expire_at is not None and ts >= order.expire_at
        if kill or expired:
            order.status = OrderStatus.CANCELLED
            order.reject_reason = "London kill switch 12:00 UTC — unfilled limit cancelled"
            cancelled.append(order)
    return cancelled
