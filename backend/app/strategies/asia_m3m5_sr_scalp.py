"""Asia M3–M5 Support/Resistance scalp (PH 7:00AM–5:00PM).

Best Asia fast-scalp setup:
  - Structure on M5: swing Support/Resistance + Asia session range
  - Trigger on closed M3: revisit level + rejection candle
  - Window: Philippines 7:00–17:00 only (stops before late London push)
  - Tight scalp TP (~1.0R) · SL beyond level + ATR pad
  - Flat if ADX wakes up (breakout risk)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session, ph_hour

SIGNAL_COOLDOWN_SECONDS = 360  # 2× M3 bars
ENTRY_PERIOD_SECONDS = 180  # M3
STRUCTURE_PERIOD_SECONDS = 300  # M5


@dataclass(frozen=True)
class Zone:
    kind: str  # "resistance" | "support"
    top: float
    bottom: float
    mid: float
    strength: float
    bar_index: int
    source: str  # "swing" | "session_range"


class AsiaM3M5SrScalpStrategy(Strategy):
    """Asia S/R scalp: M5 levels, M3 rejection entries (PH 7AM–5PM)."""

    name = "asia_m3m5_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True
    entry_period_seconds = ENTRY_PERIOD_SECONDS
    structure_period_seconds = STRUCTURE_PERIOD_SECONDS

    def __init__(
        self,
        swing_lookback: int = 3,
        zone_lookback: int = 40,
        range_lookback: int = 28,
        atr_period: int = 14,
        adx_period: int = 14,
        max_adx: float = 23.0,
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
        super().__init__(lookback=max(zone_lookback, range_lookback, atr_period * 2) + 50)
        self.swing_lookback = swing_lookback
        self.zone_lookback = zone_lookback
        self.range_lookback = range_lookback
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.max_adx = max_adx
        self.zone_atr_width = zone_atr_width
        self.touch_atr = touch_atr
        self.sl_pad_atr = sl_pad_atr
        self.reward_r = reward_r
        self.min_zone_age = min_zone_age
        self.max_zones = max_zones
        self.news_filter = news_filter
        self.asia_only = asia_only
        self.ph_start_hour = ph_start_hour
        self.ph_end_hour = ph_end_hour
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._last_signal_at: dict[str, float] = {}
        self._structure_bars: list[Candle] = []
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []
        self.last_zones: list[dict] = []
        self.last_range: dict | None = None
        self.last_session_label: str | None = None

    def set_structure_bars(self, candles: list[Candle]) -> None:
        """M5 closed bars used for Support/Resistance mapping."""
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _in_asia_scalp_hours(self, ts) -> bool:
        utc = ts if ts.tzinfo else ts
        ph = ph_hour(utc)
        return self.ph_start_hour <= ph < self.ph_end_hour

    def _session_range_zones(self, candles: list[Candle], atr: float) -> tuple[list[Zone], dict]:
        window = candles[-self.range_lookback :]
        hi = max(c.high for c in window)
        lo = min(c.low for c in window)
        mid = (hi + lo) / 2.0
        half_w = self.zone_atr_width * atr
        n = len(candles)
        zones = [
            Zone(
                kind="resistance",
                top=hi + half_w * 0.2,
                bottom=hi - half_w,
                mid=hi,
                strength=2.5,
                bar_index=n - 2,
                source="session_range",
            ),
            Zone(
                kind="support",
                top=lo + half_w,
                bottom=lo - half_w * 0.2,
                mid=lo,
                strength=2.5,
                bar_index=n - 2,
                source="session_range",
            ),
        ]
        info = {
            "high": round(hi, 2),
            "low": round(lo, 2),
            "mid": round(mid, 2),
            "width": round(hi - lo, 2),
        }
        return zones, info

    def _swing_zones(self, candles: list[Candle], atr: float) -> list[Zone]:
        n = len(candles)
        lb = self.swing_lookback
        half_w = self.zone_atr_width * atr
        zones: list[Zone] = []
        start = max(lb, n - self.zone_lookback)
        end = n - 1
        for i in range(start, end):
            if i - lb < 0 or i + lb >= n:
                continue
            hi = candles[i].high
            lo = candles[i].low
            is_high = all(
                hi >= candles[j].high for j in range(i - lb, i + lb + 1) if j != i
            )
            is_low = all(
                lo <= candles[j].low for j in range(i - lb, i + lb + 1) if j != i
            )
            age = n - 1 - i
            if age < self.min_zone_age:
                continue
            strength = 1.0 + min(2.0, age / 18.0)
            if is_high:
                zones.append(
                    Zone(
                        kind="resistance",
                        top=hi + half_w * 0.25,
                        bottom=hi - half_w,
                        mid=hi,
                        strength=strength,
                        bar_index=i,
                        source="swing",
                    )
                )
            if is_low:
                zones.append(
                    Zone(
                        kind="support",
                        top=lo + half_w,
                        bottom=lo - half_w * 0.25,
                        mid=lo,
                        strength=strength,
                        bar_index=i,
                        source="swing",
                    )
                )
        return zones

    def _merge_zones(self, zones: list[Zone], atr: float) -> list[Zone]:
        half_w = self.zone_atr_width * atr
        zones = sorted(zones, key=lambda z: (z.strength, z.bar_index), reverse=True)
        kept: list[Zone] = []
        for z in zones:
            if any(
                k.kind == z.kind and abs(k.mid - z.mid) <= half_w * 1.6 for k in kept
            ):
                continue
            kept.append(z)
            if len(kept) >= self.max_zones:
                break
        return kept

    def _touching(self, bar: Candle, zone: Zone, atr: float) -> bool:
        pad = self.touch_atr * atr
        top = zone.top + pad
        bottom = zone.bottom - pad
        return (
            bottom <= bar.low <= top
            or bottom <= bar.high <= top
            or bottom <= bar.close <= top
            or (bar.low <= bottom and bar.high >= top)
        )

    def _opposite_target(
        self, side: Side, entry: float, zones: list[Zone], atr: float
    ) -> float | None:
        if side == Side.BUY:
            resists = sorted(
                (z for z in zones if z.kind == "resistance" and z.bottom > entry),
                key=lambda z: z.bottom,
            )
            if resists:
                return resists[0].bottom - 0.08 * atr
        else:
            supports = sorted(
                (z for z in zones if z.kind == "support" and z.top < entry),
                key=lambda z: z.top,
                reverse=True,
            )
            if supports:
                return supports[0].top + 0.08 * atr
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        """`candles` = M3 entry bars. Structure comes from set_structure_bars(M5)."""
        if tick.symbol.upper() != self.SYMBOL:
            return None

        structure = self._structure_bars or candles
        need_m3 = self.atr_period + 8
        need_m5 = max(self.zone_lookback, self.range_lookback) + self.atr_period + 5
        if len(candles) < need_m3 or len(structure) < need_m5:
            self.last_block_reason = (
                f"Waiting for M3({need_m3}) + M5({need_m5}) bars"
            )
            self.last_checklist = []
            self.last_zones = []
            self.last_range = None
            return None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        asia_ok = True
        if self.asia_only:
            asia_ok = session.tier == SessionTier.ASIA and self._in_asia_scalp_hours(
                tick.timestamp
            )
        if not gate(
            "asia_session",
            asia_ok,
            session.reason
            if session.tier == SessionTier.ASIA
            else f"Need Asia PH {self.ph_start_hour}:00–{self.ph_end_hour}:00",
        ):
            self.last_block_reason = (
                f"Outside Asia M3/M5 scalp window (PH {self.ph_start_hour}AM–{self.ph_end_hour}PM)"
            )
            self.last_checklist = checks
            return None

        if self.news_filter:
            news = check_news_blackout(tick.timestamp)
            if not gate("news", not news.blocked, news.reason):
                self.last_block_reason = news.reason
                self.last_checklist = checks
                return None

        # ATR/ADX from M5 structure (more stable); entry confirm on M3 bar
        vol = true_atr(structure, self.atr_period)
        strength = adx([c.close for c in structure], self.adx_period)
        if vol is None or strength is None:
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None

        if not gate(
            "ranging_ok",
            strength <= self.max_adx,
            f"ADX={strength:.1f} (max {self.max_adx} for M3/M5 S/R)",
        ):
            self.last_block_reason = "ADX rising — skip Asia S/R fade"
            self.last_checklist = checks
            return None

        range_zones, range_info = self._session_range_zones(structure, vol)
        range_info["atr"] = round(vol, 2)
        range_info["adx"] = round(strength, 1)
        range_info["structure"] = "M5"
        range_info["entry"] = "M3"
        self.last_range = range_info

        zones = self._merge_zones(range_zones + self._swing_zones(structure, vol), vol)
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

        bar = candles[-1]  # M3 trigger bar
        support_hits = [
            z for z in zones if z.kind == "support" and self._touching(bar, z, vol)
        ]
        resist_hits = [
            z for z in zones if z.kind == "resistance" and self._touching(bar, z, vol)
        ]
        buy_ok = bool(support_hits) and bullish_confirm(bar) and bar.close > bar.open
        sell_ok = bool(resist_hits) and bearish_confirm(bar) and bar.close < bar.open

        gate("at_level", bool(support_hits or resist_hits), "M3 bar at M5 S/R")
        gate(
            "reject",
            (bullish_confirm(bar) if support_hits else False)
            or (bearish_confirm(bar) if resist_hits else False),
            "M3 rejection at support/resistance",
        )
        self.last_checklist = checks

        if not (buy_ok or sell_ok):
            self.last_block_reason = "No M3 rejection at M5 S/R"
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
                f"M3 entry / M5 S/R {side.value}: "
                f"{zone.kind} ({zone.source}) {zone.bottom:.2f}-{zone.top:.2f} · "
                f"reject · ADX={strength:.1f} · "
                f"SL beyond level · TP opp/~{self.reward_r}R · R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
