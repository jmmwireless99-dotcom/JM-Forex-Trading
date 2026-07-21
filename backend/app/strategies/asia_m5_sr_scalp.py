"""Asia M5 active scalp — PH 7:00AM–5:00PM (Manila).

Designed for live Asia gold tape (range + mean-reversion + bounce scalps):
  Path A — Asia box edge: fade session high/low after sweep+rejection → TP mid
  Path B — Local M5 S/R: fade recent swing high/low with rejection → TP ~1R
  Soft cutoff PH 16:45 (near London). Flat on news / extreme ADX only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session

SIGNAL_COOLDOWN_SECONDS = 300  # 1× M5 — more active scalps
M5_SECONDS = 300
PH = timezone(timedelta(hours=8))


class AsiaM5SrScalpStrategy(Strategy):
    """Active Asia M5 scalp: box-edge fade + local swing S/R."""

    name = "asia_m5_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        atr_period: int = 14,
        adx_period: int = 14,
        rsi_period: int = 14,
        max_adx: float = 28.0,
        edge_frac: float = 0.28,
        min_reject_wick: float = 0.22,
        swing_lookback: int = 2,
        local_lookback: int = 12,
        min_box_atr: float = 1.2,
        max_box_atr: float = 30.0,
        sl_pad_atr: float = 0.18,
        min_reward_r: float = 0.7,
        rsi_buy: float = 48.0,
        rsi_sell: float = 52.0,
        news_filter: bool = True,
        asia_only: bool = True,
        ph_start_hour: int = 7,
        ph_end_hour: int = 17,
        ph_soft_cutoff_hour: int = 16,
        ph_soft_cutoff_minute: int = 45,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(100, atr_period * 3 + 40))
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.rsi_period = rsi_period
        self.max_adx = max_adx
        self.edge_frac = edge_frac
        self.min_reject_wick = min_reject_wick
        self.swing_lookback = swing_lookback
        self.local_lookback = local_lookback
        self.min_box_atr = min_box_atr
        self.max_box_atr = max_box_atr
        self.sl_pad_atr = sl_pad_atr
        self.min_reward_r = min_reward_r
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
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
        ph = self._ph(ts)
        return (ph.hour, ph.minute) >= (
            self.ph_soft_cutoff_hour,
            self.ph_soft_cutoff_minute,
        )

    def _asia_box(
        self, candles: list[Candle], ts: datetime
    ) -> tuple[float, float, list[Candle]] | None:
        ph_now = self._ph(ts)
        day = ph_now.date()
        session_bars: list[Candle] = []
        for c in candles:
            ph = self._ph(c.open_time)
            if ph.date() != day:
                continue
            if self.ph_start_hour <= ph.hour < self.ph_end_hour:
                session_bars.append(c)
        if len(session_bars) < 4:
            return None
        hi = max(c.high for c in session_bars)
        lo = min(c.low for c in session_bars)
        if hi <= lo:
            return None
        return hi, lo, session_bars

    def _local_swings(self, candles: list[Candle]) -> tuple[float, float]:
        window = candles[-self.local_lookback :]
        return max(c.high for c in window), min(c.low for c in window)

    def _wick_fracs(self, bar: Candle) -> tuple[float, float]:
        rng = bar.high - bar.low
        if rng <= 0:
            return 0.0, 0.0
        upper = (bar.high - max(bar.open, bar.close)) / rng
        lower = (min(bar.open, bar.close) - bar.low) / rng
        return upper, lower

    def _emit(
        self,
        *,
        side: Side,
        entry: float,
        sl: float,
        tp: float,
        strength: float,
        reason: str,
        tick: Tick,
    ) -> Signal | None:
        risk = abs(entry - sl)
        if risk <= 0:
            self.last_block_reason = "Invalid risk"
            return None
        reward = abs(tp - entry)
        rr = reward / risk
        if rr < self.min_reward_r * 0.75:
            self.last_block_reason = f"R:R too small ({rr:.2f})"
            return None
        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(strength, 3),
            reason=reason + f" · R={rr:.2f}",
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )

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
            f"PH {self.ph_start_hour}:00–{self.ph_end_hour}:00",
        ):
            self.last_block_reason = "Outside Asia hours (PH 7AM–5PM)"
            self.last_checklist = checks
            return None

        if not gate(
            "pre_london",
            not self._past_soft_cutoff(tick.timestamp),
            f"Cutoff PH {self.ph_soft_cutoff_hour}:{self.ph_soft_cutoff_minute:02d}",
        ):
            self.last_block_reason = "Near London — no new Asia scalps after PH 4:45"
            self.last_checklist = checks
            return None

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        asia_ok = session.tier == SessionTier.ASIA if self.asia_only else True
        if not gate("asia_session", asia_ok, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        if len(candles) < self.atr_period + self.local_lookback + 5:
            self.last_block_reason = "Waiting for M5 history"
            self.last_checklist = checks
            return None

        bar = candles[-1]
        if not gate(
            "m5_bar",
            bar.period_seconds == M5_SECONDS,
            f"M{max(1, bar.period_seconds // 60)}",
        ):
            self.last_block_reason = "Need closed M5 bar"
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
        mom = rsi([c.close for c in candles], self.rsi_period)
        if vol is None or strength is None or mom is None:
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None

        if not gate(
            "adx_ok",
            strength <= self.max_adx,
            f"ADX={strength:.1f} (max {self.max_adx})",
        ):
            self.last_block_reason = "ADX too high for Asia scalp"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate("cooldown", cool, f"{self.signal_cooldown_seconds}s"):
            self.last_block_reason = "Scalp cooldown"
            self.last_checklist = checks
            return None

        upper_wick, lower_wick = self._wick_fracs(bar)
        box = self._asia_box(candles, tick.timestamp)
        local_hi, local_lo = self._local_swings(candles)

        # ---------- Path A: Asia session box edge fade ----------
        if box is not None:
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
                "rsi": round(mom, 1),
                "bars": len(session_bars),
                "mode": "asia_box_fade",
            }
            self.last_zones = [
                {
                    "kind": "resistance",
                    "top": round(box_hi, 2),
                    "bottom": round(box_hi - 0.3 * vol, 2),
                    "mid": round(box_hi, 2),
                    "strength": 2.5,
                    "source": "asia_box",
                },
                {
                    "kind": "support",
                    "top": round(box_lo + 0.3 * vol, 2),
                    "bottom": round(box_lo, 2),
                    "mid": round(box_lo, 2),
                    "strength": 2.5,
                    "source": "asia_box",
                },
            ]
            width_ok = self.min_box_atr * vol <= width <= self.max_box_atr * vol
            gate("box_width", width_ok, f"box={width:.2f} ATR={vol:.2f}")
            if width_ok:
                edge = self.edge_frac * width
                near_low = bar.low <= box_lo + edge
                near_high = bar.high >= box_hi - edge
                buy_a = (
                    near_low
                    and lower_wick >= self.min_reject_wick
                    and bar.close >= bar.open
                    and bar.close > box_lo
                    and mom <= self.rsi_buy
                    and (bullish_confirm(bar) or bar.close > bar.open)
                )
                sell_a = (
                    near_high
                    and upper_wick >= self.min_reject_wick
                    and bar.close <= bar.open
                    and bar.close < box_hi
                    and mom >= self.rsi_sell
                    and (bearish_confirm(bar) or bar.close < bar.open)
                )
                gate("box_edge", near_low or near_high, "At Asia box edge")
                if buy_a or sell_a:
                    side = Side.BUY if buy_a and not sell_a else Side.SELL
                    if buy_a and sell_a:
                        side = (
                            Side.BUY
                            if abs(bar.close - box_lo) <= abs(bar.close - box_hi)
                            else Side.SELL
                        )
                    entry = tick.ask if side == Side.BUY else tick.bid
                    if side == Side.BUY:
                        sl = min(box_lo, bar.low) - self.sl_pad_atr * vol
                        tp = mid
                        if tp <= entry:
                            tp = entry + max(self.min_reward_r * (entry - sl), 0.6 * vol)
                    else:
                        sl = max(box_hi, bar.high) + self.sl_pad_atr * vol
                        tp = mid
                        if tp >= entry:
                            tp = entry - max(self.min_reward_r * (sl - entry), 0.6 * vol)
                    self.last_checklist = checks
                    return self._emit(
                        side=side,
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        strength=min(1.0, (self.max_adx - strength) / self.max_adx + 0.45),
                        reason=(
                            f"M5 Asia BOX fade {side.value}: "
                            f"{box_lo:.2f}-{box_hi:.2f} mid={mid:.2f} · "
                            f"ADX={strength:.1f} RSI={mom:.1f}"
                        ),
                        tick=tick,
                    )

        # ---------- Path B: local swing S/R scalp (more frequent) ----------
        pad = 0.35 * vol
        near_local_low = bar.low <= local_lo + pad
        near_local_high = bar.high >= local_hi - pad
        buy_b = (
            near_local_low
            and lower_wick >= self.min_reject_wick
            and bar.close > bar.open
            and mom <= self.rsi_buy
            and bar.close <= (local_hi + local_lo) / 2 + 0.2 * vol
        )
        sell_b = (
            near_local_high
            and upper_wick >= self.min_reject_wick
            and bar.close < bar.open
            and mom >= self.rsi_sell
            and bar.close >= (local_hi + local_lo) / 2 - 0.2 * vol
        )
        gate("local_sr", near_local_low or near_local_high, f"swing {local_lo:.2f}-{local_hi:.2f}")
        gate(
            "reject",
            (buy_b or sell_b),
            f"wick L={lower_wick:.2f} U={upper_wick:.2f} RSI={mom:.1f}",
        )
        self.last_checklist = checks

        if not (buy_b or sell_b):
            self.last_block_reason = "No Asia M5 scalp setup (box edge or local S/R)"
            if self.last_range is None:
                self.last_range = {
                    "high": round(local_hi, 2),
                    "low": round(local_lo, 2),
                    "mid": round((local_hi + local_lo) / 2, 2),
                    "width": round(local_hi - local_lo, 2),
                    "atr": round(vol, 2),
                    "adx": round(strength, 1),
                    "rsi": round(mom, 1),
                    "mode": "local_sr",
                }
            return None

        side = Side.BUY if buy_b and not sell_b else Side.SELL
        if buy_b and sell_b:
            side = (
                Side.BUY
                if abs(bar.close - local_lo) <= abs(bar.close - local_hi)
                else Side.SELL
            )
        entry = tick.ask if side == Side.BUY else tick.bid
        mid_local = (local_hi + local_lo) / 2.0
        if side == Side.BUY:
            sl = min(local_lo, bar.low) - self.sl_pad_atr * vol
            risk = entry - sl
            tp = min(mid_local, entry + max(self.min_reward_r * risk, 0.7 * vol))
            if tp <= entry:
                tp = entry + max(self.min_reward_r * risk, 0.6 * vol)
        else:
            sl = max(local_hi, bar.high) + self.sl_pad_atr * vol
            risk = sl - entry
            tp = max(mid_local, entry - max(self.min_reward_r * risk, 0.7 * vol))
            if tp >= entry:
                tp = entry - max(self.min_reward_r * risk, 0.6 * vol)

        return self._emit(
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            strength=min(1.0, 0.55 + lower_wick * 0.2 + upper_wick * 0.2),
            reason=(
                f"M5 Asia LOCAL S/R {side.value}: "
                f"swing {local_lo:.2f}-{local_hi:.2f} · "
                f"reject · ADX={strength:.1f} RSI={mom:.1f}"
            ),
            tick=tick,
        )
