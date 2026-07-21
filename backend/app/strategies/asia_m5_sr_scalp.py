"""Asia M5 range-fade scalp — tuned to PH 7:00AM–5:00PM gold behavior.

Observed Asia (Manila daytime) tape on XAUUSD:
  - Mostly range / chop — not clean trends
  - Stretch candles often reverse next (mean reversion)
  - Best edge: fade Asia session box high/low after rejection wick
  - Breakouts during Asia are frequently false — do not chase
  - Scalp TP toward box mid; stop new entries near London (after PH 4:30)

Rules:
  1. Closed M5 only · PH 7:00–17:00 (hard) · soft cutoff 16:30
  2. Build Asia box = high/low of M5 bars since PH 7:00 today
  3. BUY only near box low + bullish rejection · SELL near box high + bearish rejection
  4. Close must reclaim inside box (liquidity sweep fade)
  5. SL beyond box edge + ATR pad · TP at box mid (~Asia scalp)
  6. Flat if ADX high, box too thin/wide, news, or breakout acceptance
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session, ph_hour

SIGNAL_COOLDOWN_SECONDS = 600  # 2× M5
M5_SECONDS = 300
PH = timezone(timedelta(hours=8))


class AsiaM5SrScalpStrategy(Strategy):
    """Asia box fade scalp for Manila 7AM–5PM gold."""

    name = "asia_m5_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        atr_period: int = 14,
        adx_period: int = 14,
        max_adx: float = 20.0,
        edge_frac: float = 0.18,
        min_reject_wick: float = 0.35,
        min_box_atr: float = 2.0,
        max_box_atr: float = 18.0,
        sl_pad_atr: float = 0.20,
        min_reward_r: float = 0.85,
        news_filter: bool = True,
        asia_only: bool = True,
        ph_start_hour: int = 7,
        ph_end_hour: int = 17,
        ph_soft_cutoff_hour: int = 16,
        ph_soft_cutoff_minute: int = 30,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(80, atr_period * 3 + 40))
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.max_adx = max_adx
        self.edge_frac = edge_frac
        self.min_reject_wick = min_reject_wick
        self.min_box_atr = min_box_atr
        self.max_box_atr = max_box_atr
        self.sl_pad_atr = sl_pad_atr
        self.min_reward_r = min_reward_r
        self.news_filter = news_filter
        self.asia_only = asia_only
        self.ph_start_hour = ph_start_hour
        self.ph_end_hour = ph_end_hour
        self.ph_soft_cutoff_hour = ph_soft_cutoff_hour
        self.ph_soft_cutoff_minute = ph_soft_cutoff_minute
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []
        self.last_zones: list[dict] = []
        self.last_range: dict | None = None
        self.last_session_label: str | None = None

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _ph(self, ts: datetime) -> datetime:
        return ts.astimezone(PH)

    def _in_asia_hours(self, ts: datetime) -> bool:
        ph = self._ph(ts)
        return self.ph_start_hour <= ph.hour < self.ph_end_hour

    def _past_soft_cutoff(self, ts: datetime) -> bool:
        """No new Asia scalps after PH 16:30 — London risk rises."""
        ph = self._ph(ts)
        return (ph.hour, ph.minute) >= (
            self.ph_soft_cutoff_hour,
            self.ph_soft_cutoff_minute,
        )

    def _asia_box(self, candles: list[Candle], ts: datetime) -> tuple[float, float, list[Candle]] | None:
        """High/low of today's Asia M5 bars from PH session open."""
        ph_now = self._ph(ts)
        day = ph_now.date()
        session_bars: list[Candle] = []
        for c in candles:
            ph = self._ph(c.open_time)
            if ph.date() != day:
                continue
            if self.ph_start_hour <= ph.hour < self.ph_end_hour:
                session_bars.append(c)
        if len(session_bars) < 6:
            return None
        hi = max(c.high for c in session_bars)
        lo = min(c.low for c in session_bars)
        if hi <= lo:
            return None
        return hi, lo, session_bars

    def _wick_fracs(self, bar: Candle) -> tuple[float, float]:
        rng = bar.high - bar.low
        if rng <= 0:
            return 0.0, 0.0
        upper = (bar.high - max(bar.open, bar.close)) / rng
        lower = (min(bar.open, bar.close) - bar.low) / rng
        return upper, lower

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        if not gate(
            "asia_hours",
            self._in_asia_hours(tick.timestamp),
            f"PH {self.ph_start_hour}:00–{self.ph_end_hour}:00 only",
        ):
            self.last_block_reason = "Outside Asia M5 scalp hours (PH 7AM–5PM)"
            self.last_checklist = checks
            return None

        if not gate(
            "pre_london",
            not self._past_soft_cutoff(tick.timestamp),
            f"Soft cutoff PH {self.ph_soft_cutoff_hour}:{self.ph_soft_cutoff_minute:02d}",
        ):
            self.last_block_reason = "Near London open — no new Asia scalps after PH 4:30"
            self.last_checklist = checks
            return None

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        asia_ok = session.tier == SessionTier.ASIA if self.asia_only else True
        if not gate("asia_session", asia_ok, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        need = self.atr_period + 20
        if len(candles) < need:
            self.last_block_reason = f"Waiting for {need} M5 bars"
            self.last_checklist = checks
            self.last_zones = []
            self.last_range = None
            return None

        bar = candles[-1]
        if not gate(
            "m5_bar",
            bar.period_seconds == M5_SECONDS,
            f"Need closed M5 (got M{max(1, bar.period_seconds // 60)})",
        ):
            self.last_block_reason = "asia_m5_sr_scalp requires closed M5 bars"
            self.last_checklist = checks
            return None

        if self.news_filter:
            news = check_news_blackout(tick.timestamp)
            if not gate("news", not news.blocked, news.reason):
                self.last_block_reason = news.reason
                self.last_checklist = checks
                return None

        vol = true_atr(candles, self.atr_period)
        strength = adx([c.close for c in candles], self.adx_period)
        if vol is None or strength is None:
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None

        if not gate(
            "ranging_ok",
            strength <= self.max_adx,
            f"ADX={strength:.1f} (max {self.max_adx} — Asia fade only)",
        ):
            self.last_block_reason = "ADX rising — Asia breakout risk, no fade"
            self.last_checklist = checks
            return None

        box = self._asia_box(candles, tick.timestamp)
        if box is None:
            self.last_block_reason = "Asia box warming (need ≥6 M5 bars since PH 7AM)"
            self.last_checklist = checks
            self.last_range = None
            self.last_zones = []
            return None
        box_hi, box_lo, session_bars = box
        width = box_hi - box_lo
        mid = (box_hi + box_lo) / 2.0

        self.last_range = {
            "high": round(box_hi, 2),
            "low": round(box_lo, 2),
            "mid": round(mid, 2),
            "width": round(width, 2),
            "atr": round(vol, 2),
            "adx": round(strength, 1),
            "bars": len(session_bars),
            "mode": "asia_box_fade",
        }
        self.last_zones = [
            {
                "kind": "resistance",
                "top": round(box_hi, 2),
                "bottom": round(box_hi - 0.25 * vol, 2),
                "mid": round(box_hi, 2),
                "strength": 2.5,
                "source": "asia_box",
            },
            {
                "kind": "support",
                "top": round(box_lo + 0.25 * vol, 2),
                "bottom": round(box_lo, 2),
                "mid": round(box_lo, 2),
                "strength": 2.5,
                "source": "asia_box",
            },
        ]

        width_ok = self.min_box_atr * vol <= width <= self.max_box_atr * vol
        if not gate(
            "box_width",
            width_ok,
            f"Asia box={width:.2f} vs ATR={vol:.2f}",
        ):
            self.last_block_reason = "Asia box too tight or too wide for scalp"
            self.last_checklist = checks
            return None

        # Breakout acceptance — close clearly outside box → do not fade
        outside = bar.close > box_hi + 0.15 * vol or bar.close < box_lo - 0.15 * vol
        if not gate("inside_box", not outside, "Close accepted outside Asia box"):
            self.last_block_reason = "Breakout acceptance — stand aside (no chase)"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate("cooldown", cool, f"{self.signal_cooldown_seconds}s between scalps"):
            self.last_block_reason = "Scalp cooldown"
            self.last_checklist = checks
            return None

        edge = self.edge_frac * width
        near_low = bar.low <= box_lo + edge or min(bar.open, bar.close) <= box_lo + edge
        near_high = bar.high >= box_hi - edge or max(bar.open, bar.close) >= box_hi - edge
        upper_wick, lower_wick = self._wick_fracs(bar)

        # Liquidity-sweep style: wick through edge, close back inside toward mid
        buy_reject = (
            near_low
            and lower_wick >= self.min_reject_wick
            and bar.close > bar.open
            and bar.close > box_lo
            and bar.close < mid
            and bullish_confirm(bar)
        )
        sell_reject = (
            near_high
            and upper_wick >= self.min_reject_wick
            and bar.close < bar.open
            and bar.close < box_hi
            and bar.close > mid
            and bearish_confirm(bar)
        )

        gate("at_edge", near_low or near_high, "Price at Asia box edge")
        gate(
            "reject_wick",
            (lower_wick >= self.min_reject_wick and near_low)
            or (upper_wick >= self.min_reject_wick and near_high),
            f"wick L={lower_wick:.2f} U={upper_wick:.2f}",
        )
        self.last_checklist = checks

        if not (buy_reject or sell_reject):
            self.last_block_reason = "No Asia box edge fade (need sweep + rejection)"
            return None

        if buy_reject and sell_reject:
            # Prefer closer edge
            if abs(bar.close - box_lo) <= abs(bar.close - box_hi):
                sell_reject = False
            else:
                buy_reject = False

        side = Side.BUY if buy_reject else Side.SELL
        entry = tick.ask if side == Side.BUY else tick.bid

        if side == Side.BUY:
            sl = box_lo - self.sl_pad_atr * vol
            risk = entry - sl
            if risk <= 0:
                self.last_block_reason = "Invalid BUY risk"
                return None
            tp = mid
            min_tp = entry + self.min_reward_r * risk
            if tp < min_tp:
                tp = min(min_tp, box_hi - 0.1 * vol)
        else:
            sl = box_hi + self.sl_pad_atr * vol
            risk = sl - entry
            if risk <= 0:
                self.last_block_reason = "Invalid SELL risk"
                return None
            tp = mid
            min_tp = entry - self.min_reward_r * risk
            if tp > min_tp:
                tp = max(min_tp, box_lo + 0.1 * vol)

        reward = abs(tp - entry)
        rr = reward / risk if risk else 0.0
        if rr < self.min_reward_r * 0.80:
            self.last_block_reason = f"R:R too small ({rr:.2f})"
            return None

        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, (self.max_adx - strength) / self.max_adx + 0.4), 3),
            reason=(
                f"M5 Asia box fade {side.value} (PH 7–5): "
                f"box {box_lo:.2f}-{box_hi:.2f} mid={mid:.2f} · "
                f"edge sweep+reject · ADX={strength:.1f} · "
                f"SL beyond box · TP mid · R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
