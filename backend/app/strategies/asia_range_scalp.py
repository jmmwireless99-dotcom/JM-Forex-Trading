"""Asia session range scalping for XAUUSD on ranging M5 candles.

Recommended Asia setup (why this beats trend tools overnight):
  - Gold in Asia often chops inside a box — EMA trend strategies get chopped
  - Best edge: fade extremes of a defined range with rejection + RSI
  - Tight structure SL beyond the range; TP at mid-range (scalp, ~1R)
  - Stand aside if ADX wakes up (London prep / breakout risk)
"""

from __future__ import annotations

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session

SIGNAL_COOLDOWN_SECONDS = 600  # 2× M5 bars between scalps


class AsiaRangeScalpStrategy(Strategy):
    """Fade Asia range highs/lows on closed M5 ranging candles."""

    name = "asia_range_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        range_lookback: int = 20,
        atr_period: int = 14,
        adx_period: int = 14,
        rsi_period: int = 14,
        max_adx: float = 22.0,
        rsi_buy: float = 35.0,
        rsi_sell: float = 65.0,
        edge_atr: float = 0.25,
        min_range_atr: float = 1.8,
        max_range_atr: float = 8.0,
        sl_pad_atr: float = 0.25,
        tp_frac_to_mid: float = 1.0,
        min_reward_r: float = 0.9,
        news_filter: bool = True,
        asia_only: bool = True,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(range_lookback, adx_period * 2) + 40)
        self.range_lookback = range_lookback
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.rsi_period = rsi_period
        self.max_adx = max_adx
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.edge_atr = edge_atr
        self.min_range_atr = min_range_atr
        self.max_range_atr = max_range_atr
        self.sl_pad_atr = sl_pad_atr
        self.tp_frac_to_mid = tp_frac_to_mid
        self.min_reward_r = min_reward_r
        self.news_filter = news_filter
        self.asia_only = asia_only
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []
        self.last_range: dict | None = None

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        need = self.range_lookback + self.atr_period + 5
        if len(candles) < need:
            self.last_block_reason = f"Waiting for {need} M5 bars"
            self.last_checklist = []
            return None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        session = classify_session(tick.timestamp)
        asia_ok = (
            session.tier == SessionTier.ASIA
            if self.asia_only
            else session.label in {"asia", "asia_off"}
        )
        if not gate("asia_session", asia_ok, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        if self.news_filter:
            news = check_news_blackout(tick.timestamp)
            if not gate("news", not news.blocked, news.reason):
                self.last_block_reason = news.reason
                self.last_checklist = checks
                return None

        window = candles[-self.range_lookback :]
        range_high = max(c.high for c in window)
        range_low = min(c.low for c in window)
        mid = (range_high + range_low) / 2.0
        width = range_high - range_low
        vol = true_atr(candles, self.atr_period)
        strength = adx([c.close for c in candles], self.adx_period)
        mom = rsi([c.close for c in candles], self.rsi_period)
        if None in (vol, strength, mom):
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None
        assert vol is not None and strength is not None and mom is not None

        self.last_range = {
            "high": round(range_high, 2),
            "low": round(range_low, 2),
            "mid": round(mid, 2),
            "width": round(width, 2),
            "atr": round(vol, 2),
            "adx": round(strength, 1),
        }

        if not gate(
            "ranging",
            strength <= self.max_adx,
            f"ADX={strength:.1f} (max {self.max_adx} for range scalp)",
        ):
            self.last_block_reason = "ADX rising — Asia breakout risk, no scalp"
            self.last_checklist = checks
            return None

        width_ok = self.min_range_atr * vol <= width <= self.max_range_atr * vol
        if not gate(
            "range_width",
            width_ok,
            f"width={width:.2f} vs ATR={vol:.2f}",
        ):
            self.last_block_reason = "Range too tight or too wide for scalp"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate("cooldown", cool, f"{self.signal_cooldown_seconds}s between scalps"):
            self.last_block_reason = "Scalp cooldown"
            self.last_checklist = checks
            return None

        bar = candles[-1]
        edge = self.edge_atr * vol
        near_low = bar.low <= range_low + edge or bar.close <= range_low + edge
        near_high = bar.high >= range_high - edge or bar.close >= range_high - edge
        buy_ok = (
            near_low
            and mom <= self.rsi_buy
            and bullish_confirm(bar)
            and bar.close > bar.open
            and bar.close < mid
        )
        sell_ok = (
            near_high
            and mom >= self.rsi_sell
            and bearish_confirm(bar)
            and bar.close < bar.open
            and bar.close > mid
        )

        gate("edge", near_low or near_high, "Price at Donchian range edge")
        gate(
            "rsi",
            (mom <= self.rsi_buy) or (mom >= self.rsi_sell),
            f"RSI={mom:.1f}",
        )
        gate(
            "reject",
            bullish_confirm(bar) if near_low else bearish_confirm(bar) if near_high else False,
            "Rejection / confirm candle at edge",
        )
        self.last_checklist = checks

        if not (buy_ok or sell_ok):
            self.last_block_reason = "No Asia range fade setup on this M5"
            return None

        side = Side.BUY if buy_ok else Side.SELL
        entry = tick.ask if side == Side.BUY else tick.bid

        if side == Side.BUY:
            sl = range_low - self.sl_pad_atr * vol
            # Scalp TP toward mid (or slightly past for fill room)
            tp = mid if self.tp_frac_to_mid >= 1.0 else entry + (mid - entry) * self.tp_frac_to_mid
            risk = entry - sl
            if risk <= 0:
                self.last_block_reason = "Invalid BUY risk"
                return None
            # Ensure minimum R; if mid is too close, push TP
            min_tp = entry + self.min_reward_r * risk
            if tp < min_tp:
                tp = min_tp
            # Cap TP at range high so we don't target breakout
            tp = min(tp, range_high - 0.1 * vol)
        else:
            sl = range_high + self.sl_pad_atr * vol
            tp = mid if self.tp_frac_to_mid >= 1.0 else entry - (entry - mid) * self.tp_frac_to_mid
            risk = sl - entry
            if risk <= 0:
                self.last_block_reason = "Invalid SELL risk"
                return None
            min_tp = entry - self.min_reward_r * risk
            if tp > min_tp:
                tp = min_tp
            tp = max(tp, range_low + 0.1 * vol)

        reward = abs(tp - entry)
        rr = reward / risk if risk else 0.0
        if rr < self.min_reward_r * 0.85:
            self.last_block_reason = f"R:R too small ({rr:.2f})"
            return None

        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None
        tf = f"M{max(1, bar.period_seconds // 60)}"
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, (self.max_adx - strength) / self.max_adx + 0.35), 3),
            reason=(
                f"{tf} Asia range scalp {side.value}: "
                f"fade {'low' if side == Side.BUY else 'high'} "
                f"[{range_low:.2f}-{range_high:.2f}] mid={mid:.2f} · "
                f"ADX={strength:.1f} RSI={mom:.1f} · "
                f"SL beyond range · TP mid · R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
