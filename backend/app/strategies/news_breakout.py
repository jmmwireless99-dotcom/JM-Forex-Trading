"""Post-release momentum strategy for high-impact USD news (XAUUSD).

Arms automatically from 1 hour before scheduled NFP/CPI/FOMC/PCE prints
through 1 hour after — PH evening/night only (7PM–7AM). Entries fire on
post-spike M5 breaks (+5 to +60m after release).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timezone

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import (
    bearish_confirm,
    bullish_confirm,
    structure_levels,
    true_atr,
)
from app.strategies.news_calendar import (
    check_news_trading_window,
    should_run_news_strategy,
)
from app.strategies.session import SessionTier, classify_session


@dataclass
class PendingBreak:
    """A directional break awaiting retest confirmation before entry."""

    side: Side
    level: float
    atr: float
    bar_index: int
    event: str


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
        require_retest: bool | None = None,
        retest_valid_bars: int | None = None,
        retest_pad_atr: float | None = None,
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.pre_range_bars = pre_range_bars
        self.min_body_atr = min_body_atr
        self.min_break_atr = min_break_atr
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.min_bars_between_signals = min_bars_between_signals
        self.max_trades_per_day = max_trades_per_day
        # Safer default: wait for price to retest the broken level with a
        # rejection candle instead of chasing the initial post-spike break —
        # gold whipsaws hard in the first minute after high-impact USD news.
        self.require_retest = (
            settings.news_breakout_require_retest
            if require_retest is None
            else require_retest
        )
        self.retest_valid_bars = (
            int(settings.news_breakout_retest_valid_bars)
            if retest_valid_bars is None
            else retest_valid_bars
        )
        self.retest_pad_atr = (
            float(settings.news_breakout_retest_pad_atr)
            if retest_pad_atr is None
            else retest_pad_atr
        )
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []
        self._last_signal_bar_ts: object | None = None
        self._trades_today: date | None = None
        self._trades_count = 0
        self._pending: PendingBreak | None = None

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

        cur_idx = len(bars) - 1
        cur = bars[-1]
        pre = bars[-(self.pre_range_bars + 1) : -1]
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

        # A break was already flagged on a prior bar — resolve it (retest / timeout)
        # before scanning for a brand-new break on this same bar.
        if self._pending is not None:
            signal = self._resolve_pending(bars, cur, cur_idx, tick)
            if signal is not None:
                return signal
            if self._pending is not None:
                return None
            # Pending timed out this bar — fall through to scan for a new break.

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
        level = 0.0
        if body >= self.min_body_atr * atr and body_dir > 0:
            if cur.close >= pre_high + self.min_break_atr * atr:
                side = Side.BUY
                level = pre_high
        elif body >= self.min_body_atr * atr and body_dir < 0:
            if cur.close <= pre_low - self.min_break_atr * atr:
                side = Side.SELL
                level = pre_low

        if side is None:
            self.last_block_reason = (
                "Waiting for post-spike directional break (body + range break)"
            )
            return None

        if self.require_retest:
            self._pending = PendingBreak(
                side=side,
                level=level,
                atr=atr,
                bar_index=cur_idx,
                event=trade_window.event or "news",
            )
            self.last_block_reason = (
                f"Post-spike break detected ({side.value}) — waiting retest of "
                f"{level:.2f} within {self.retest_valid_bars} bars"
            )
            self.last_checklist.append(self.last_block_reason)
            return None

        reason = (
            f"NewsBreakout {side.value} · {trade_window.event} · "
            f"post-spike break {'above' if side == Side.BUY else 'below'} {level:.2f}"
        )
        return self._fire(side, reason, bars, atr, tick, cur)

    def _resolve_pending(
        self, bars: list[Candle], cur: Candle, cur_idx: int, tick: Tick
    ) -> Signal | None:
        pending = self._pending
        assert pending is not None
        age = cur_idx - pending.bar_index
        if age > self.retest_valid_bars:
            self.last_block_reason = (
                f"Retest window missed for {pending.event} break — momentum "
                "already priced in, skipping"
            )
            self.last_checklist.append(self.last_block_reason)
            self._pending = None
            return None

        pad = self.retest_pad_atr * pending.atr
        if pending.side == Side.BUY:
            retested = cur.low <= pending.level + pad
            rejected = bullish_confirm(cur) and cur.close > pending.level - pad * 0.5
        else:
            retested = cur.high >= pending.level - pad
            rejected = bearish_confirm(cur) and cur.close < pending.level + pad * 0.5

        if not (retested and rejected):
            self.last_block_reason = (
                f"Waiting retest+rejection at {pending.level:.2f} "
                f"({self.retest_valid_bars - age} bars left)"
            )
            self.last_checklist.append(self.last_block_reason)
            return None

        reason = (
            f"NewsBreakout {pending.side.value} · {pending.event} · "
            f"retest {pending.level:.2f} + rejection candle"
        )
        signal = self._fire(pending.side, reason, bars, pending.atr, tick, cur)
        self._pending = None
        return signal

    def _fire(
        self,
        side: Side,
        reason: str,
        bars: list[Candle],
        atr: float,
        tick: Tick,
        cur: Candle,
    ) -> Signal:
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
