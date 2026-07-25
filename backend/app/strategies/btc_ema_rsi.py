"""BTCUSD best desk strategy: EMA200 trend + EMA20/50 pullback + RSI + engulf/pin.

Crypto trades nearly 24/7 — no gold Asia/London session map. Manual select + save.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import (
    bearish_confirm,
    bullish_confirm,
    structure_levels,
    true_atr,
)
from app.strategies.indicators import ema, rsi
from app.strategies.patterns import (
    bearish_engulfing,
    bearish_pin_bar,
    bullish_engulfing,
    bullish_pin_bar,
)


class BtcEmaRsiScalpStrategy(Strategy):
    """Best BTCUSD pullback scalp for this desk — trend + RSI + pattern."""

    name = "BTC_EMA_RSI_Scalp"
    candle_driven = True
    symbol = "BTCUSD"

    def __init__(
        self,
        lookback: int = 240,
        *,
        ema_trend: int = 200,
        ema_fast: int = 20,
        ema_slow: int = 50,
        rsi_period: int = 14,
        rsi_buy: tuple[float, float] = (38.0, 52.0),
        rsi_sell: tuple[float, float] = (48.0, 62.0),
        news_filter: bool | None = None,
        min_bars_between_signals: int = 8,
        allow_soft_confirm: bool = False,
        reward_r: float = 2.2,
        min_stop_atr: float = 1.6,
        min_tp_atr: float = 3.0,
        max_stop_atr: float = 3.2,
    ) -> None:
        super().__init__(lookback=lookback)
        self.ema_trend = ema_trend
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.min_bars_between_signals = min_bars_between_signals
        self.allow_soft_confirm = allow_soft_confirm
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.max_stop_atr = max_stop_atr
        settings = get_settings()
        # BTC desk ignores FX USD news blackout by default.
        self.news_filter = False if news_filter is None else news_filter
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []
        self._last_signal_bar_ts: object | None = None
        self._last_signal_side: Side | None = None
        _ = settings  # reserved for future BTC session toggles

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if (tick.symbol or "").upper() not in {"BTCUSD", "BTCUSDT"}:
            self.last_block_reason = "BTC_EMA_RSI waits for BTCUSD ticks"
            return None

        bars = self._structure_bars or candles
        # Keep only BTC bars — never fall back to gold/mixed history.
        bars = [
            c
            for c in bars
            if (c.symbol or "").upper() in {"BTCUSD", "BTCUSDT", ""}
        ]
        self.last_checklist = []
        self.last_block_reason = None

        if not bars:
            self.last_block_reason = "No BTCUSD bars in structure history"
            return None
        if len(bars) < self.ema_trend + 5:
            self.last_block_reason = f"Need {self.ema_trend + 5}+ M5 BTC bars"
            return None

        closes = [c.close for c in bars]
        e200 = ema(closes, self.ema_trend)
        e20 = ema(closes, self.ema_fast)
        e50 = ema(closes, self.ema_slow)
        rsi_v = rsi(closes, self.rsi_period)
        atr = true_atr(bars, 14)
        if None in (e200, e20, e50, rsi_v, atr) or atr is None or atr <= 0:
            self.last_block_reason = "BTC indicators warming up"
            return None

        cur = bars[-1]
        prev = bars[-2]
        price = cur.close
        band = max(0.25 * atr, 5.0)

        zone_lo = min(e20, e50)
        zone_hi = max(e20, e50)
        in_zone = zone_lo - band <= price <= zone_hi + band
        touched_fast = (
            abs(cur.low - e20) <= band
            or abs(cur.high - e20) <= band
            or abs(price - e20) <= band
        )
        near_fast = in_zone or touched_fast

        bull_pat = bullish_engulfing(prev, cur) or bullish_pin_bar(cur)
        bear_pat = bearish_engulfing(prev, cur) or bearish_pin_bar(cur)
        bull_soft = (
            self.allow_soft_confirm
            and bullish_confirm(cur)
            and cur.close >= prev.close
        )
        bear_soft = (
            self.allow_soft_confirm
            and bearish_confirm(cur)
            and cur.close <= prev.close
        )

        buy_rsi = self.rsi_buy[0] <= rsi_v <= self.rsi_buy[1]
        sell_rsi = self.rsi_sell[0] <= rsi_v <= self.rsi_sell[1]
        ema_sep = abs(e20 - e50) >= 0.08 * atr
        uptrend = price > e200 and e20 >= e50 and ema_sep
        downtrend = price < e200 and e20 <= e50 and ema_sep

        self.last_checklist = [
            f"BTC EMA200={e200:.1f} EMA20={e20:.1f} EMA50={e50:.1f}",
            f"RSI={rsi_v:.1f} ATR={atr:.1f} ema_sep={ema_sep}",
            f"zone={zone_lo:.1f}-{zone_hi:.1f} near={near_fast}",
            f"pattern bull={bull_pat}/{bull_soft} bear={bear_pat}/{bear_soft}",
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
                        f"BTC cooldown ({self.min_bars_between_signals} M5 bars)"
                    )
                    return None
            except StopIteration:
                pass

        side: Side | None = None
        reason = ""
        if uptrend and near_fast and buy_rsi and (bull_pat or bull_soft):
            side = Side.BUY
            tag = (
                "engulf"
                if bullish_engulfing(prev, cur)
                else "pin"
                if bullish_pin_bar(cur)
                else "soft"
            )
            reason = (
                f"BTC_EMA BUY · >EMA200 · retest EMA20/50 · RSI {rsi_v:.0f} · {tag}"
            )
        elif downtrend and near_fast and sell_rsi and (bear_pat or bear_soft):
            side = Side.SELL
            tag = (
                "engulf"
                if bearish_engulfing(prev, cur)
                else "pin"
                if bearish_pin_bar(cur)
                else "soft"
            )
            reason = (
                f"BTC_EMA SELL · <EMA200 · retest EMA20/50 · RSI {rsi_v:.0f} · {tag}"
            )
        else:
            self.last_block_reason = (
                "No BTC confluence "
                f"(trend={'up' if uptrend else 'down' if downtrend else 'flat'} "
                f"rsi={rsi_v:.0f} near={near_fast} pat={bull_pat or bear_pat})"
            )
            return None

        levels = structure_levels(
            side,
            entry=tick.ask if side == Side.BUY else tick.bid,
            candles=bars,
            atr=atr,
            swing_lookback=8,
            reward_r=self.reward_r,
            min_stop_atr=self.min_stop_atr,
            max_stop_atr=self.max_stop_atr,
            min_tp_atr=self.min_tp_atr,
            anchor_sl=(e50 - 0.4 * atr) if side == Side.BUY else (e50 + 0.4 * atr),
        )
        self._last_signal_bar_ts = cur.open_time or cur.timestamp
        self._last_signal_side = side
        return Signal(
            strategy=self.name,
            symbol="BTCUSD",
            side=side,
            strength=0.88,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
