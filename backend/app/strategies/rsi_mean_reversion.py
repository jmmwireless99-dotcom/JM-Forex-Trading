from __future__ import annotations

from app.models.domain import Side, Signal, Tick
from app.strategies.base import Strategy


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class RsiMeanReversionStrategy(Strategy):
    name = "rsi_mean_reversion"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70) -> None:
        super().__init__(lookback=period + 30)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self._last_side: dict[str, Side] = {}

    def evaluate(self, tick: Tick) -> Signal | None:
        value = rsi(self.prices(tick.symbol), self.period)
        if value is None:
            return None

        last = self._last_side.get(tick.symbol)
        if value <= self.oversold and last != Side.BUY:
            self._last_side[tick.symbol] = Side.BUY
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=Side.BUY,
                strength=(self.oversold - value) / self.oversold,
                reason=f"RSI oversold at {value:.1f}",
            )
        if value >= self.overbought and last != Side.SELL:
            self._last_side[tick.symbol] = Side.SELL
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=Side.SELL,
                strength=(value - self.overbought) / (100 - self.overbought),
                reason=f"RSI overbought at {value:.1f}",
            )
        return None