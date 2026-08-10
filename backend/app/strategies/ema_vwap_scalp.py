"""9/21 EMA crossover + VWAP filter scalp (M5).

Long: 9 EMA crosses above 21 EMA with price above session VWAP.
Short: 9 EMA crosses below 21 EMA with price below session VWAP.
SL at recent swing; TP at 1:2 risk-reward (or hold to SL/TP — no auto reverse).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.indicators import ema_crossover, vwap
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


class EmaVwapScalpStrategy(Strategy):
    name = "EMA_VWAP_Scalp"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 120,
        *,
        ema_fast: int = 9,
        ema_slow: int = 21,
        reward_r: float = 2.0,
        news_filter: bool | None = None,
        session_filter: bool | None = None,
        min_bars_between_signals: int = 3,
    ) -> None:
        super().__init__(lookback=lookback)
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.reward_r = reward_r
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

        min_bars = self.ema_slow + 5
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
        cross = ema_crossover(closes, self.ema_fast, self.ema_slow)
        vwap_v = vwap(bars)
        atr = true_atr(bars, 14)
        if cross is None or vwap_v is None or atr is None or atr <= 0:
            self.last_block_reason = "Indicators warming up or no crossover"
            return None

        cur = bars[-1]
        price = cur.close
        self.last_checklist = [
            f"EMA{self.ema_fast}/{self.ema_slow} cross={cross}",
            f"VWAP={vwap_v:.2f} price={price:.2f}",
            f"ATR={atr:.2f}",
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
        if cross == "bull" and price > vwap_v:
            side = Side.BUY
            reason = (
                f"EMA_VWAP BUY · EMA{self.ema_fast}↑EMA{self.ema_slow} · "
                f"price>{vwap_v:.2f} VWAP"
            )
        elif cross == "bear" and price < vwap_v:
            side = Side.SELL
            reason = (
                f"EMA_VWAP SELL · EMA{self.ema_fast}↓EMA{self.ema_slow} · "
                f"price<{vwap_v:.2f} VWAP"
            )
        else:
            self.last_block_reason = (
                f"No confluence (cross={cross} price vs VWAP "
                f"{'above' if price > vwap_v else 'below'})"
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
            swing_lookback=3,
            atr_pad=0.2,
            min_stop_atr=0.8,
            reward_r=self.reward_r,
            min_tp_atr=1.6,
        )
        self._last_signal_bar_ts = cur.open_time or cur.timestamp
        self._last_signal_side = side
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.9,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
