"""EMA 200 + EMA 20/50 retest + RSI 14 + engulfing/pin bar scalp (M5)."""

from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.indicators import ema, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.patterns import (
    bearish_engulfing,
    bearish_pin_bar,
    bullish_engulfing,
    bullish_pin_bar,
)
from app.strategies.session import SessionTier, classify_session


class EmaRsiScalpStrategy(Strategy):
    name = "EMA_RSI_Scalp"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        ema_trend: int = 200,
        ema_fast: int = 20,
        ema_slow: int = 50,
        rsi_period: int = 14,
        rsi_buy: tuple[float, float] = (35.0, 55.0),
        rsi_sell: tuple[float, float] = (45.0, 65.0),
        news_filter: bool | None = None,
        session_filter: bool | None = None,
    ) -> None:
        super().__init__(lookback=lookback)
        self.ema_trend = ema_trend
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self._structure_bars: list[Candle] = []

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None

        if len(bars) < self.ema_trend + 5:
            self.last_block_reason = f"Need {self.ema_trend + 5}+ M5 bars"
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
        e200 = ema(closes, self.ema_trend)
        e20 = ema(closes, self.ema_fast)
        e50 = ema(closes, self.ema_slow)
        rsi_v = rsi(closes, self.rsi_period)
        atr = true_atr(bars, 14)
        if None in (e200, e20, e50, rsi_v, atr) or atr is None or atr <= 0:
            self.last_block_reason = "Indicators warming up"
            return None

        cur = bars[-1]
        prev = bars[-2]
        price = cur.close
        band = max(0.25 * atr, 0.5)

        # Dynamic S/R zone between EMA20 and EMA50 (wider band so paper ATR doesn't starve entries)
        zone_lo = min(e20, e50)
        zone_hi = max(e20, e50)
        in_zone = zone_lo - band <= price <= zone_hi + band
        touched_fast = (
            abs(cur.low - e20) <= band
            or abs(cur.high - e20) <= band
            or abs(price - e20) <= band
        )

        bull_pat = bullish_engulfing(prev, cur) or bullish_pin_bar(cur)
        bear_pat = bearish_engulfing(prev, cur) or bearish_pin_bar(cur)
        # Soft confirm: directional close when RSI+zone already aligned
        bull_soft = cur.close > cur.open and cur.close >= prev.close
        bear_soft = cur.close < cur.open and cur.close <= prev.close

        buy_rsi = self.rsi_buy[0] <= rsi_v <= self.rsi_buy[1]
        sell_rsi = self.rsi_sell[0] <= rsi_v <= self.rsi_sell[1]
        # Trend filter: price vs EMA200. EMA20/50 stack is preferred but not mandatory
        # when they are nearly flat (common right after paper seed).
        flat_stack = abs(e20 - e50) <= band
        uptrend = price > e200 and (e20 >= e50 or flat_stack)
        downtrend = price < e200 and (e20 <= e50 or flat_stack)

        self.last_checklist = [
            f"EMA200={e200:.2f} EMA20={e20:.2f} EMA50={e50:.2f}",
            f"RSI={rsi_v:.1f} ATR={atr:.2f}",
            f"zone={zone_lo:.2f}-{zone_hi:.2f} in_zone={in_zone}",
            f"pattern bull={bull_pat}/{bull_soft} bear={bear_pat}/{bear_soft}",
        ]

        side: Side | None = None
        reason = ""
        if uptrend and (in_zone or touched_fast) and buy_rsi and (bull_pat or bull_soft):
            side = Side.BUY
            tag = "engulf" if bullish_engulfing(prev, cur) else "pin" if bullish_pin_bar(cur) else "soft"
            reason = (
                f"EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · "
                f"RSI {rsi_v:.0f} · {tag}"
            )
        elif downtrend and (in_zone or touched_fast) and sell_rsi and (bear_pat or bear_soft):
            side = Side.SELL
            tag = "engulf" if bearish_engulfing(prev, cur) else "pin" if bearish_pin_bar(cur) else "soft"
            reason = (
                f"EMA_RSI SELL · trend<EMA200 · retest EMA20/50 · "
                f"RSI {rsi_v:.0f} · {tag}"
            )
        else:
            self.last_block_reason = (
                "No confluence "
                f"(trend={'up' if uptrend else 'down' if downtrend else 'flat'} "
                f"rsi={rsi_v:.0f} zone={in_zone} pat={bull_pat or bear_pat or bull_soft or bear_soft})"
            )
            return None

        levels = structure_levels(
            side,
            entry=tick.ask if side == Side.BUY else tick.bid,
            candles=bars,
            atr=atr,
            reward_r=1.6,
            min_stop_atr=1.0,
            min_tp_atr=1.8,
        )
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.85,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
