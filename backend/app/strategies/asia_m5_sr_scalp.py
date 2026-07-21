"""Asia M5 Support/Resistance scalp — PH 7:00AM–5:00PM.

Dedicated Asia daytime strategy:
  - Timeframe: closed M5 candles only
  - Edge: fade Support (buy) / Resistance (sell) with rejection confirm
  - Levels: M5 swing S/R + Asia session range high/low
  - Window: Philippines 7:00–17:00 (stops before late London push)
  - SL beyond level + ATR pad · TP opposite S/R or ~1.0R scalp
  - Flat if ADX wakes up / news / outside Asia hours
"""

from __future__ import annotations

from datetime import timezone

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.asia_sr_scalp import AsiaSrScalpStrategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session, ph_hour

SIGNAL_COOLDOWN_SECONDS = 600  # 2× M5
M5_SECONDS = 300


class AsiaM5SrScalpStrategy(AsiaSrScalpStrategy):
    """Pure M5 S/R fade scalp for Asia session PH 7AM–5PM."""

    name = "asia_m5_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        swing_lookback: int = 3,
        zone_lookback: int = 40,
        range_lookback: int = 28,
        atr_period: int = 14,
        adx_period: int = 14,
        max_adx: float = 22.0,
        zone_atr_width: float = 0.28,
        touch_atr: float = 0.20,
        sl_pad_atr: float = 0.22,
        reward_r: float = 1.0,
        min_zone_age: int = 2,
        max_zones: int = 8,
        news_filter: bool = True,
        asia_only: bool = True,
        ph_start_hour: int = 7,
        ph_end_hour: int = 17,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(
            swing_lookback=swing_lookback,
            zone_lookback=zone_lookback,
            range_lookback=range_lookback,
            atr_period=atr_period,
            adx_period=adx_period,
            max_adx=max_adx,
            zone_atr_width=zone_atr_width,
            touch_atr=touch_atr,
            sl_pad_atr=sl_pad_atr,
            reward_r=reward_r,
            min_zone_age=min_zone_age,
            max_zones=max_zones,
            news_filter=news_filter,
            asia_only=asia_only,
            signal_cooldown_seconds=signal_cooldown_seconds,
        )
        self.ph_start_hour = ph_start_hour
        self.ph_end_hour = ph_end_hour

    def _in_asia_hours(self, ts) -> bool:
        ph = ph_hour(ts.astimezone(timezone.utc))
        return self.ph_start_hour <= ph < self.ph_end_hour

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        # Hard PH 7AM–5PM gate (in addition to session tier)
        hours_ok = self._in_asia_hours(tick.timestamp)
        if not gate(
            "asia_hours",
            hours_ok,
            f"PH {self.ph_start_hour}:00–{self.ph_end_hour}:00 only",
        ):
            self.last_block_reason = "Outside Asia M5 scalp hours (PH 7AM–5PM)"
            self.last_checklist = checks
            return None

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        asia_ok = session.tier == SessionTier.ASIA if self.asia_only else True
        if not gate("asia_session", asia_ok, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        need = max(self.zone_lookback, self.range_lookback) + self.atr_period + 5
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
            f"ADX={strength:.1f} (max {self.max_adx})",
        ):
            self.last_block_reason = "ADX rising — no Asia M5 S/R fade"
            self.last_checklist = checks
            return None

        range_zones, range_info = self._session_range_zones(candles, vol)
        range_info["atr"] = round(vol, 2)
        range_info["adx"] = round(strength, 1)
        self.last_range = range_info

        zones = self._merge_zones(range_zones + self._swing_zones(candles, vol), vol)
        self.last_zones = [
            {
                "kind": z.kind,
                "top": round(z.top, 2),
                "bottom": round(z.bottom, 2),
                "mid": round(z.mid, 2),
                "strength": round(z.strength, 2),
                "source": z.source,
            }
            for z in zones
        ]
        if not gate("sr_levels", bool(zones), f"{len(zones)} M5 S/R levels"):
            self.last_block_reason = "No M5 support/resistance levels"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate("cooldown", cool, f"{self.signal_cooldown_seconds}s between scalps"):
            self.last_block_reason = "Scalp cooldown"
            self.last_checklist = checks
            return None

        support_hits = [
            z for z in zones if z.kind == "support" and self._touching(bar, z, vol)
        ]
        resist_hits = [
            z for z in zones if z.kind == "resistance" and self._touching(bar, z, vol)
        ]
        buy_ok = bool(support_hits) and bullish_confirm(bar) and bar.close > bar.open
        sell_ok = bool(resist_hits) and bearish_confirm(bar) and bar.close < bar.open

        gate("at_level", bool(support_hits or resist_hits), "Price at M5 S/R")
        gate(
            "reject",
            (bullish_confirm(bar) if support_hits else False)
            or (bearish_confirm(bar) if resist_hits else False),
            "M5 rejection at support/resistance",
        )
        self.last_checklist = checks

        if not (buy_ok or sell_ok):
            self.last_block_reason = "No M5 S/R revisit + rejection"
            return None

        if buy_ok and sell_ok:
            s = min(support_hits, key=lambda z: abs(bar.close - z.mid))
            r = min(resist_hits, key=lambda z: abs(bar.close - z.mid))
            if abs(bar.close - s.mid) <= abs(bar.close - r.mid):
                sell_ok = False
            else:
                buy_ok = False

        side = Side.BUY if buy_ok else Side.SELL
        zone = (
            min(support_hits, key=lambda z: abs(bar.close - z.mid))
            if side == Side.BUY
            else min(resist_hits, key=lambda z: abs(bar.close - z.mid))
        )
        entry = tick.ask if side == Side.BUY else tick.bid

        if side == Side.BUY:
            sl = zone.bottom - self.sl_pad_atr * vol
            risk = entry - sl
            if risk <= 0:
                self.last_block_reason = "Invalid BUY risk"
                return None
            r_tp = entry + self.reward_r * risk
            opp = self._opposite_target(side, entry, zones, vol)
            tp = min(opp, r_tp) if opp is not None and opp > entry else r_tp
        else:
            sl = zone.top + self.sl_pad_atr * vol
            risk = sl - entry
            if risk <= 0:
                self.last_block_reason = "Invalid SELL risk"
                return None
            r_tp = entry - self.reward_r * risk
            opp = self._opposite_target(side, entry, zones, vol)
            tp = max(opp, r_tp) if opp is not None and opp < entry else r_tp

        reward = abs(tp - entry)
        rr = reward / risk if risk else 0.0
        if rr < self.reward_r * 0.85:
            self.last_block_reason = f"R:R too small ({rr:.2f})"
            return None

        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, 0.5 + 0.15 * zone.strength), 3),
            reason=(
                f"M5 Asia S/R scalp {side.value} (PH 7–5): "
                f"{zone.kind} ({zone.source}) {zone.bottom:.2f}-{zone.top:.2f} · "
                f"reject · ADX={strength:.1f} · "
                f"SL beyond level · TP opp/S/R or {self.reward_r}R · R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
