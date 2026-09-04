"""Post-release momentum strategy for high-impact USD news (XAUUSD).

Arms automatically from 1 hour before scheduled NFP/CPI/FOMC/PCE prints
through 1 hour after — PH evening/night only (7PM–7AM). Entries fire on
post-spike M5 breaks (+5 to +60m after release).
"""

from __future__ import annotations

from datetime import date, timezone

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.news_calendar import (
    check_news_trading_window,
    should_run_news_strategy,
)
from app.strategies.session import SessionTier, classify_session


class NewsBreakoutStrategy(Strategy):
    name = "NewsBreakout"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 120,
        *,
        pre_range_bars: int = 6,
        min_body_atr: float = 0.85,
        min_break_atr: float = 0.35,
        reward_r: float = 2.0,
        min_stop_atr: float = 3.0,
        min_tp_atr: float = 6.0,
        min_bars_between_signals: int = 4,
        max_trades_per_day: int = 2,
    ) -> None:
        super().__init__(lookback=lookback)
        self.pre_range_bars = pre_range_bars
        self.min_body_atr = min_body_atr
        self.min_break_atr = min_break_atr
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.min_bars_between_signals = min_bars_between_signals
        self.max_trades_per_day = max_trades_per_day
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []
        self._last_signal_bar_ts: object | None = None
        self._trades_today: date | None = None
        self._trades_count = 0

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _roll_day(self, ts) -> None:
        day = ts.astimezone(timezone.utc).date()
        if self._trades_today != day:
            self._trades_today = day
            self._trades_count = 0

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None
        self._roll_day(tick.timestamp)

        if len(bars) < self.pre_range_bars + 5:
            self.last_block_reason = f"Need {self.pre_range_bars + 5}+ M5 bars"
            return None

        window = classify_session(tick.timestamp)
        if window.tier == SessionTier.AVOID:
            self.last_block_reason = window.reason
            return None

        armed = should_run_news_strategy(tick.timestamp)
        if not armed.active:
            self.last_block_reason = armed.reason or "NewsBreakout not armed"
            return None

        trade_window = check_news_trading_window(tick.timestamp)
        if not trade_window.active:
            self.last_block_reason = trade_window.reason
            return None

        if self._trades_count >= self.max_trades_per_day:
            self.last_block_reason = (
                f"NewsBreakout: max {self.max_trades_per_day} trades today"
            )
            return None

        atr = true_atr(bars, 14)
        if atr is None or atr <= 0:
            self.last_block_reason = "ATR warming up"
            return None

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

        pre = bars[-(self.pre_range_bars + 1) : -1]
        cur = bars[-1]
        pre_high = max(c.high for c in pre)
        pre_low = min(c.low for c in pre)
        body = abs(cur.close - cur.open)
        body_dir = 1 if cur.close >= cur.open else -1

        self.last_checklist = [
            f"event={trade_window.event} +{trade_window.minutes_from_release}m",
            f"pre_range H/L={pre_high:.2f}/{pre_low:.2f}",
            f"body={body:.2f} ATR={atr:.2f}",
            f"trades_today={self._trades_count}/{self.max_trades_per_day}",
        ]

        side: Side | None = None
        reason = ""
        if body >= self.min_body_atr * atr and body_dir > 0:
            if cur.close >= pre_high + self.min_break_atr * atr:
                side = Side.BUY
                reason = (
                    f"NewsBreakout BUY · {trade_window.event} · "
                    f"post-spike break above {pre_high:.2f}"
                )
        elif body >= self.min_body_atr * atr and body_dir < 0:
            if cur.close <= pre_low - self.min_break_atr * atr:
                side = Side.SELL
                reason = (
                    f"NewsBreakout SELL · {trade_window.event} · "
                    f"post-spike break below {pre_low:.2f}"
                )

        if side is None:
            self.last_block_reason = (
                "Waiting for post-spike directional break (body + range break)"
            )
            return None

        entry = tick.ask if side == Side.BUY else tick.bid
        levels = structure_levels(
            side,
            entry=entry,
            candles=bars,
            atr=atr,
            swing_lookback=4,
            atr_pad=0.55,
            min_stop_atr=self.min_stop_atr,
            reward_r=self.reward_r,
            min_tp_atr=self.min_tp_atr,
        )
        self._last_signal_bar_ts = cur.open_time or cur.timestamp
        self._trades_count += 1
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.92,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
