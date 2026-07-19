from __future__ import annotations

from app.models.domain import Side, Signal, Tick
from app.strategies.base import Strategy


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    result = sum(values[:period]) / period
    for price in values[period:]:
        result = price * k + result * (1 - k)
    return result


class EmaCrossoverStrategy(Strategy):
    """Classic fast/slow EMA crossover for FX majors."""

    name = "ema_crossover"

    def __init__(self, fast: int = 9, slow: int = 21) -> None:
        super().__init__(lookback=slow + 40)
        self.fast = fast
        self.slow = slow
        self._prev_diff: dict[str, float] = {}

    def evaluate(self, tick: Tick) -> Signal | None:
        series = self.prices(tick.symbol)
        fast_ema = ema(series, self.fast)
        slow_ema = ema(series, self.slow)
        if fast_ema is None or slow_ema is None:
            return None

        diff = fast_ema - slow_ema
        prev = self._prev_diff.get(tick.symbol)
        self._prev_diff[tick.symbol] = diff
        if prev is None:
            return None

        if prev <= 0 < diff:
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=Side.BUY,
                strength=min(1.0, abs(diff) / max(tick.mid * 0.0001, 1e-9)),
                reason=f"EMA{self.fast} crossed above EMA{self.slow}",
            )
        if prev >= 0 > diff:
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=Side.SELL,
                strength=min(1.0, abs(diff) / max(tick.mid * 0.0001, 1e-9)),
                reason=f"EMA{self.fast} crossed below EMA{self.slow}",
            )
        return None