"""London Judas async helpers — process M1/M5 bars, manage Asian range + kill switch.

Used by TradingEngine; can also be imported for standalone scripts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.models.domain import Candle, Order, OrderStatus, Tick
from app.strategies.london_judas_sweep import LondonJudasSweepStrategy
from app.strategies.london_session import (
    calculate_asian_range,
    is_past_pending_kill,
    is_london_entry_window,
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
    """Thin façade around LondonJudasSweepStrategy + session math."""

    def __init__(self) -> None:
        self.strategy = LondonJudasSweepStrategy()

    def snapshot(self, bars_m5: list[Candle], ts: datetime) -> LondonDeskSnapshot:
        asian = calculate_asian_range(bars_m5, as_of=ts)
        return LondonDeskSnapshot(
            in_entry_window=is_london_entry_window(ts),
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
            last_block=self.strategy.last_block_reason,
            checklist=list(self.strategy.last_checklist),
            pending_note="Unfilled LIMIT orders auto-cancel at 12:00 UTC",
        )

    def evaluate(
        self,
        bars_m5: list[Candle],
        tick: Tick,
        *,
        bars_m1: list[Candle] | None = None,
    ):
        self.strategy.set_structure_bars(bars_m5)
        if bars_m1:
            self.strategy.set_m1_bars(bars_m1)
        return self.strategy.on_bar(bars_m5, tick)

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
