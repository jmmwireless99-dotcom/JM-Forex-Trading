"""GOLD# / XAUUSD micro-scalp — short-term momentum on M5.

Follows live gold tape (desk XAUUSD ↔ broker GOLD#):
  • Fast EMA 8/21 bias (no EMA200 wait)
  • RSI 7 momentum band
  • Impulse candle or fresh EMA cross
  • Tight ATR stops (~0.85×ATR SL · ~1.5R TP) for quick in/out
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.indicators import ema, ema_crossover, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


class GoldMicroScalpStrategy(Strategy):
    name = "Gold_Micro_Scalp"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 80,
        *,
        ema_fast: int = 8,
        ema_slow: int = 21,
        rsi_period: int = 7,
        # Wide bands — gold micro-scalps chase short impulse, not mean-revert.
        rsi_buy: tuple[float, float] = (48.0, 88.0),
        rsi_sell: tuple[float, float] = (12.0, 52.0),
        impulse_atr: float = 0.40,
        reward_r: float = 1.5,
        min_stop_atr: float = 0.85,
        min_tp_atr: float = 1.25,
        news_filter: bool | None = None,
        session_filter: bool | None = None,
        min_bars_between_signals: int = 2,
    ) -> None:
        super().__init__(lookback=lookback)
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.impulse_atr = impulse_atr
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.min_bars_between_signals = min_bars_between_signals
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []
        self._last_signal_bar_ts: object | None = None
        self._last_signal_side: Side | None = None

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None

        min_bars = self.ema_slow + self.rsi_period + 3
        if len(bars) < min_bars:
            self.last_block_reason = f"Need {min_bars}+ M5 bars"
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

        closes = [c.close for c in bars]
        e_fast = ema(closes, self.ema_fast)
        e_slow = ema(closes, self.ema_slow)
        rsi_v = rsi(closes, self.rsi_period)
        rsi_prev = rsi(closes[:-1], self.rsi_period)
        atr = true_atr(bars, 14)
        cross = ema_crossover(closes, self.ema_fast, self.ema_slow)
        if None in (e_fast, e_slow, rsi_v, atr) or atr is None or atr <= 0:
            self.last_block_reason = "Indicators warming up"
            return None

        cur = bars[-1]
        prev = bars[-2]
        price = cur.close
        body = abs(cur.close - cur.open)
        range_ = max(cur.high - cur.low, 1e-9)
        bull_impulse = (
            cur.close > cur.open
            and body >= self.impulse_atr * atr
            and cur.close >= prev.close
        )
        bear_impulse = (
            cur.close < cur.open
            and body >= self.impulse_atr * atr
            and cur.close <= prev.close
        )
        bull_bias = e_fast > e_slow and price >= e_slow
        bear_bias = e_fast < e_slow and price <= e_slow
        buy_rsi = self.rsi_buy[0] <= rsi_v <= self.rsi_buy[1]
        sell_rsi = self.rsi_sell[0] <= rsi_v <= self.rsi_sell[1]
        # Impulse continuation may pin RSI near 0/100 — still valid short-term chase.
        if bull_impulse and rsi_v >= self.rsi_buy[0]:
            buy_rsi = True
        if bear_impulse and rsi_v <= self.rsi_sell[1]:
            sell_rsi = True
        rsi_rising = rsi_prev is None or rsi_v >= rsi_prev
        rsi_falling = rsi_prev is None or rsi_v <= rsi_prev

        self.last_checklist = [
            f"EMA{self.ema_fast}={e_fast:.2f} EMA{self.ema_slow}={e_slow:.2f}",
            f"RSI{self.rsi_period}={rsi_v:.1f} ATR={atr:.2f} body={body:.2f}",
            f"cross={cross} impulse bull={bull_impulse} bear={bear_impulse}",
            f"range={range_:.2f} bias={'up' if bull_bias else 'down' if bear_bias else 'flat'}",
        ]

        if self._last_signal_bar_ts is not None:
            try:
                idx = next(
                    i
                    for i, b in enumerate(bars)
                    if (b.open_time or b.timestamp) == self._last_signal_bar_ts
                )
                if len(bars) - 1 - idx < self.min_bars_between_signals:
                    self.last_block_reason = (
                        f"Cooldown ({self.min_bars_between_signals} M5 bars)"
                    )
                    return None
            except StopIteration:
                pass

        side: Side | None = None
        reason = ""
        tag = ""
        if bull_bias and buy_rsi and rsi_rising and (bull_impulse or cross == "bull"):
            side = Side.BUY
            tag = "cross" if cross == "bull" else "impulse"
            reason = (
                f"GOLD_MICRO BUY · EMA{self.ema_fast}>{self.ema_slow} · "
                f"RSI{self.rsi_period} {rsi_v:.0f} · {tag}"
            )
        elif bear_bias and sell_rsi and rsi_falling and (bear_impulse or cross == "bear"):
            side = Side.SELL
            tag = "cross" if cross == "bear" else "impulse"
            reason = (
                f"GOLD_MICRO SELL · EMA{self.ema_fast}<{self.ema_slow} · "
                f"RSI{self.rsi_period} {rsi_v:.0f} · {tag}"
            )
        else:
            self.last_block_reason = (
                "No short-term confluence "
                f"(bias={'up' if bull_bias else 'down' if bear_bias else 'flat'} "
                f"rsi={rsi_v:.0f} impulse={bull_impulse or bear_impulse} cross={cross})"
            )
            return None

        if self._last_signal_side is not None and side != self._last_signal_side:
            if self._last_signal_bar_ts is not None:
                try:
                    idx = next(
                        i
                        for i, b in enumerate(bars)
                        if (b.open_time or b.timestamp) == self._last_signal_bar_ts
                    )
                    if len(bars) - 1 - idx < self.min_bars_between_signals + 2:
                        self.last_block_reason = "Flip blocked — wait for setup to mature"
                        return None
                except StopIteration:
                    pass

        entry = tick.ask if side == Side.BUY else tick.bid
        levels = structure_levels(
            side,
            entry=entry,
            candles=bars,
            atr=atr,
            swing_lookback=2,
            atr_pad=0.25,
            min_stop_atr=self.min_stop_atr,
            reward_r=self.reward_r,
            min_tp_atr=self.min_tp_atr,
        )
        self._last_signal_bar_ts = cur.open_time or cur.timestamp
        self._last_signal_side = side
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
