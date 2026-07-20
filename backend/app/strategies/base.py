from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque

from app.models.domain import Signal, Tick


class Strategy(ABC):
    name: str = "base"

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback
        self._history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback))

    def feed(self, tick: Tick) -> None:
        """Update price history without evaluating a signal."""
        self._history[tick.symbol].append(tick.mid)

    def on_tick(self, tick: Tick) -> Signal | None:
        self.feed(tick)
        return self.evaluate(tick)

    def prices(self, symbol: str) -> list[float]:
        return list(self._history[symbol])

    @abstractmethod
    def evaluate(self, tick: Tick) -> Signal | None:
        raise NotImplementedError