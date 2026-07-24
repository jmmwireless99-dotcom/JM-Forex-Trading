"""Idle placeholder — no auto signals. Manual BUY/SELL still works."""

from __future__ import annotations

from app.models.domain import Signal, Tick
from app.strategies.base import Strategy


class ManualOnlyStrategy(Strategy):
    name = "manual_only"
    candle_driven = False

    def evaluate(self, tick: Tick) -> Signal | None:
        return None
