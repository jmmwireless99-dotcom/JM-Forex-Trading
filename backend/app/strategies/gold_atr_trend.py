from __future__ import annotations

from datetime import timezone

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import (
    bearish_confirm,
    bullish_confirm,
    pulled_into_zone,
    recent_stretch_above,
    recent_stretch_below,
    structure_levels,
    true_atr,
)
from app.strategies.indicators import adx, ema

SIGNAL_COOLDOWN_SECONDS = 900


class GoldAtrTrendStrategy(Strategy):
    """XAUUSD ATR trend-pullback on closed signal candles (default M5).

    Enters only after:
      - clear EMA trend + ADX strength
      - impulse stretch, pullback into EMA, confirmation close
      - structure SL / R-multiple TP from true ATR
    """

    name = "gold_atr_trend"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        fast: int = 21,
        slow: int = 55,
        atr_period: int = 14,
        adx_period: int = 14,
        pullback_atr: float = 0.70,
        min_atr: float = 1.0,
        min_adx: float = 28.0,
        session_filter: bool = False,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
        reward_r: float = 2.0,
    ) -> None:
        super().__init__(lookback=slow + atr_period + 80)
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.pullback_atr = pullback_atr
        self.min_atr = min_atr
        self.min_adx = min_adx
        self.session_filter = session_filter
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self.reward_r = reward_r
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []

    def _in_session(self, tick: Tick) -> bool:
        if not self.session_filter:
            hour = tick.timestamp.astimezone(timezone.utc).hour
            return 7 <= hour < 20
        hour = tick.timestamp.astimezone(timezone.utc).hour
        return 7 <= hour < 20

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        if len(candles) < self.slow + 5:
            self.last_block_reason = f"Waiting for {self.slow + 5} M5 bars"
            return None
        if not self._in_session(tick):
            self.last_block_reason = "Outside London/NY hours"
            return None

        closes = [c.close for c in candles]
        fast_ema = ema(closes, self.fast)
        slow_ema = ema(closes, self.slow)
        vol = true_atr(candles, self.atr_period)
        strength = adx(closes, self.adx_period)
        if None in (fast_ema, slow_ema, vol, strength):
            self.last_block_reason = "Indicators warming up"
            return None
        assert fast_ema is not None and slow_ema is not None
        assert vol is not None and strength is not None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        if not gate("atr", vol >= self.min_atr, f"ATR={vol:.2f}"):
            self.last_block_reason = "ATR too low"
            self.last_checklist = checks
            return None
        if not gate("adx", strength >= self.min_adx, f"ADX={strength:.1f}"):
            self.last_block_reason = f"ADX {strength:.1f} — weak trend"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        if tick.timestamp.timestamp() - last_at < self.signal_cooldown_seconds:
            self.last_block_reason = "Cooldown between M5 setups"
            self.last_checklist = checks
            return None

        bar = candles[-1]
        band = self.pullback_atr * vol
        bullish = fast_ema > slow_ema
        bearish = fast_ema < slow_ema
        stretch_buy = recent_stretch_above(candles, fast_ema + 0.5 * vol)
        stretch_sell = recent_stretch_below(candles, fast_ema - 0.5 * vol)
        in_zone = pulled_into_zone(candles, mid=fast_ema, band=band)

        buy_ready = (
            bullish
            and stretch_buy
            and in_zone
            and bullish_confirm(bar)
            and bar.close >= fast_ema
        )
        sell_ready = (
            bearish
            and stretch_sell
            and in_zone
            and bearish_confirm(bar)
            and bar.close <= fast_ema
        )

        gate("trend", bullish or bearish, "EMA trend")
        gate("stretch", stretch_buy if bullish else stretch_sell, "Impulse stretch")
        gate("pullback", in_zone, "EMA pullback zone")
        gate(
            "confirm",
            (bullish_confirm(bar) if bullish else bearish_confirm(bar)),
            "Confirmation candle",
        )
        self.last_checklist = checks

        if not (buy_ready or sell_ready):
            self.last_block_reason = "No M5 pullback confirmation"
            return None

        side = Side.BUY if buy_ready else Side.SELL
        entry = tick.ask if side == Side.BUY else tick.bid
        levels = structure_levels(
            side,
            entry=entry,
            candles=candles,
            atr=vol,
            reward_r=self.reward_r,
            min_stop_atr=1.4,
            min_tp_atr=2.8,
        )
        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None

        tf = f"M{max(1, candles[-1].period_seconds // 60)}"
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, strength / 45.0), 3),
            reason=(
                f"{tf} ATR trend {side.value}: EMA pullback confirm · "
                f"ADX={strength:.1f} ATR={vol:.2f} · "
                f"SL risk={levels.risk} TP={levels.reward_r}R"
            ),
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
        )
