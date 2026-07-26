"""True trend/breakout + hard SL/TP (Donchian channel break · ATR · EMA200 filter).

Classic directional bot style — NO grid / NO martingale.
Expect win rate ~45–60%; edge from R:R ≥ 2.5 and controlled DD.
Best automated on New York USD drive (UTC 16–20 / PH 12AM–4AM).
"""

from __future__ import annotations

from datetime import timezone

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.indicators import adx, ema
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


class TrendBreakoutAtrStrategy(Strategy):
    name = "Trend_Breakout_ATR"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        channel_period: int = 20,
        ema_trend: int = 200,
        adx_period: int = 14,
        min_adx: float = 18.0,
        min_break_atr: float = 0.15,
        reward_r: float = 2.5,
        min_stop_atr: float = 1.2,
        min_tp_atr: float = 2.8,
        max_stop_atr: float = 2.8,
        min_bars_between_signals: int = 10,
        news_filter: bool | None = None,
        session_filter: bool | None = None,
        # Prefer NY + optional London when session_filter is on.
        kill_zones_utc: tuple[tuple[int, int], ...] = ((7, 11), (16, 20)),
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.channel_period = max(8, int(channel_period))
        self.ema_trend = int(ema_trend)
        self.adx_period = int(adx_period)
        self.min_adx = float(min_adx)
        self.min_break_atr = float(min_break_atr)
        self.reward_r = float(reward_r)
        self.min_stop_atr = float(min_stop_atr)
        self.min_tp_atr = float(min_tp_atr)
        self.max_stop_atr = float(max_stop_atr)
        self.min_bars_between_signals = max(1, int(min_bars_between_signals))
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.kill_zones_utc = kill_zones_utc
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []
        self._last_signal_bar_ts: object | None = None
        self._last_signal_side: Side | None = None

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _in_kill_zone(self, ts) -> bool:
        hour = ts.astimezone(timezone.utc).hour
        return any(a <= hour < b for a, b in self.kill_zones_utc)

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None

        need = max(self.ema_trend + 5, self.channel_period + 5, self.adx_period * 2 + 5)
        if len(bars) < need:
            self.last_block_reason = f"Need {need}+ M5 bars for Trend_Breakout_ATR"
            return None

        if self.news_filter:
            news = check_news_blackout(tick.timestamp)
            if news.blocked:
                self.last_block_reason = news.reason
                return None

        if self.session_filter:
            window = classify_session(tick.timestamp)
            if window.tier == SessionTier.AVOID:
                self.last_block_reason = window.reason
                return None
            if not self._in_kill_zone(tick.timestamp):
                self.last_block_reason = (
                    "Trend breakout kill zones — London UTC 07–11 / NY UTC 16–20"
                )
                return None

        closes = [c.close for c in bars]
        e200 = ema(closes, self.ema_trend)
        atr = true_atr(bars, 14)
        adx_v = adx(closes, self.adx_period)
        if e200 is None or atr is None or atr <= 0 or adx_v is None:
            self.last_block_reason = "Indicators warming up"
            return None

        # Prior Donchian channel (exclude current bar).
        prior = bars[-(self.channel_period + 1) : -1]
        if len(prior) < self.channel_period:
            self.last_block_reason = "Channel warming up"
            return None
        channel_high = max(c.high for c in prior)
        channel_low = min(c.low for c in prior)
        cur = bars[-1]
        prev = bars[-2]
        width = channel_high - channel_low
        if width < 0.8 * atr:
            self.last_block_reason = "Channel too tight — skip chop breakout"
            return None

        if adx_v < self.min_adx:
            self.last_block_reason = f"ADX {adx_v:.1f} < {self.min_adx} — weak trend"
            return None

        break_buf = self.min_break_atr * atr
        buy_break = (
            cur.close > channel_high + break_buf
            and prev.close <= channel_high + break_buf
            and cur.close > e200
        )
        sell_break = (
            cur.close < channel_low - break_buf
            and prev.close >= channel_low - break_buf
            and cur.close < e200
        )

        self.last_checklist = [
            f"Donchian{self.channel_period} H={channel_high:.2f} L={channel_low:.2f}",
            f"EMA200={e200:.2f} ADX={adx_v:.1f} ATR={atr:.2f}",
            f"close={cur.close:.2f} kill_zone={self._in_kill_zone(tick.timestamp)}",
        ]

        side: Side | None = None
        if buy_break and not sell_break:
            side = Side.BUY
        elif sell_break and not buy_break:
            side = Side.SELL
        else:
            self.last_block_reason = (
                "Waiting Donchian close-break with EMA200 trend filter"
            )
            return None

        if (
            self._last_signal_bar_ts is not None
            and self._last_signal_side == side
        ):
            # Spacing: count bars since last same-side signal timestamp.
            try:
                ages = [
                    i
                    for i, b in enumerate(bars)
                    if b.timestamp == self._last_signal_bar_ts
                ]
                if ages:
                    age = len(bars) - 1 - ages[-1]
                    if age < self.min_bars_between_signals:
                        self.last_block_reason = (
                            f"Cooldown between breakouts ({age}/"
                            f"{self.min_bars_between_signals} bars)"
                        )
                        return None
            except Exception:
                pass

        entry = tick.ask if side == Side.BUY else tick.bid
        # SL beyond opposite channel side (breakout invalidation).
        if side == Side.BUY:
            anchor = channel_low - 0.25 * atr
        else:
            anchor = channel_high + 0.25 * atr

        levels = structure_levels(
            side,
            entry=entry,
            candles=bars,
            atr=atr,
            swing_lookback=max(6, self.channel_period // 2),
            reward_r=self.reward_r,
            min_stop_atr=self.min_stop_atr,
            max_stop_atr=self.max_stop_atr,
            min_tp_atr=self.min_tp_atr,
            anchor_sl=anchor,
        )
        risk = abs(entry - levels.stop_loss)
        if risk <= 0:
            self.last_block_reason = "Invalid breakout risk"
            return None
        reward = abs(levels.take_profit - entry)
        if reward / risk < 2.0:
            self.last_block_reason = f"R:R {reward / risk:.2f} < 2.0 — skip"
            return None

        self._last_signal_bar_ts = cur.timestamp
        self._last_signal_side = side
        reason = (
            f"Trend_Breakout {side.value} · Donchian{self.channel_period} "
            f"{'↑' if side == Side.BUY else '↓'} · EMA200 filter · "
            f"ADX {adx_v:.0f} · SL {levels.stop_loss} · TP {levels.take_profit}"
        )
        self.last_checklist.append(f"R={reward / risk:.2f} entry={entry:.2f}")

        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.88,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
