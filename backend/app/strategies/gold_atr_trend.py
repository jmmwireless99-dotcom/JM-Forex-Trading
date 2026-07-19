from __future__ import annotations

from datetime import timezone

from app.models.domain import Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.ema_crossover import ema


def atr(values: list[float], period: int = 14) -> float | None:
    """True-range proxy from mid closes (good enough for tick/sim feeds)."""
    if len(values) < period + 1:
        return None
    ranges: list[float] = []
    for i in range(-period, 0):
        prev = values[i - 1]
        cur = values[i]
        ranges.append(abs(cur - prev))
    return sum(ranges) / period


class GoldAtrTrendStrategy(Strategy):
    """XAUUSD ATR trend-pullback — recommended JM Forex gold desk strategy.

    Why this setup for gold:
    - Gold trends hard but whipsaws on fixed-pip stops → ATR adapts to volatility
    - Pullback entries beat naked EMA crosses in noisy gold tape
    - London/NY session filter avoids thin Asian liquidity spikes
    - Wider SL (1.8×ATR) + 2.4R target fits gold's expansion profile
    """

    name = "gold_atr_trend"
    SYMBOL = "XAUUSD"

    def __init__(
        self,
        fast: int = 21,
        slow: int = 55,
        atr_period: int = 14,
        pullback_atr: float = 0.45,
        sl_atr: float = 1.8,
        tp_atr: float = 2.7,
        min_atr: float = 0.35,
        session_filter: bool = False,
    ) -> None:
        super().__init__(lookback=slow + atr_period + 40)
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self.pullback_atr = pullback_atr
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr
        self.min_atr = min_atr
        self.session_filter = session_filter
        self._armed: dict[str, Side | None] = {}
        self._last_signal_bar: dict[str, int] = {}
        self._bars: dict[str, int] = {}

    def _in_session(self, tick: Tick) -> bool:
        if not self.session_filter:
            return True
        # London 07–16 UTC, New York 13–20 UTC → trade 07–20 UTC
        hour = tick.timestamp.astimezone(timezone.utc).hour
        return 7 <= hour < 20

    def evaluate(self, tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        if not self._in_session(tick):
            return None

        series = self.prices(tick.symbol)
        self._bars[tick.symbol] = self._bars.get(tick.symbol, 0) + 1
        fast_ema = ema(series, self.fast)
        slow_ema = ema(series, self.slow)
        vol = atr(series, self.atr_period)
        if fast_ema is None or slow_ema is None or vol is None:
            return None
        if vol < self.min_atr:
            return None  # chop / too quiet

        # Cool-down so we don't spam the same impulse
        last_bar = self._last_signal_bar.get(tick.symbol, -999)
        if self._bars[tick.symbol] - last_bar < 8:
            return None

        bullish = fast_ema > slow_ema
        bearish = fast_ema < slow_ema
        dist_to_fast = tick.mid - fast_ema
        armed = self._armed.get(tick.symbol)

        # Arm pullback when price stretches away from fast EMA, then wait for reclaim
        if bullish and dist_to_fast >= self.pullback_atr * vol:
            self._armed[tick.symbol] = Side.BUY
        elif bearish and dist_to_fast <= -self.pullback_atr * vol:
            self._armed[tick.symbol] = Side.SELL
        elif not bullish and not bearish:
            self._armed[tick.symbol] = None

        # Entry: pullback toward EMA then turn back with trend
        if armed == Side.BUY and bullish and abs(dist_to_fast) <= self.pullback_atr * vol:
            if tick.mid >= fast_ema:
                return self._build(tick, Side.BUY, vol, fast_ema, slow_ema)
        if armed == Side.SELL and bearish and abs(dist_to_fast) <= self.pullback_atr * vol:
            if tick.mid <= fast_ema:
                return self._build(tick, Side.SELL, vol, fast_ema, slow_ema)
        return None

    def _build(
        self, tick: Tick, side: Side, vol: float, fast_ema: float, slow_ema: float
    ) -> Signal:
        self._armed[tick.symbol] = None
        self._last_signal_bar[tick.symbol] = self._bars[tick.symbol]
        sl_dist = self.sl_atr * vol
        tp_dist = self.tp_atr * vol
        if side == Side.BUY:
            sl = tick.ask - sl_dist
            tp = tick.ask + tp_dist
        else:
            sl = tick.bid + sl_dist
            tp = tick.bid - tp_dist

        strength = min(1.0, abs(fast_ema - slow_ema) / max(vol, 1e-9))
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=strength,
            reason=(
                f"Gold ATR trend {side.value}: EMA{self.fast}/EMA{self.slow} "
                f"pullback, ATR={vol:.2f}, SL={self.sl_atr}×ATR TP={self.tp_atr}×ATR"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
