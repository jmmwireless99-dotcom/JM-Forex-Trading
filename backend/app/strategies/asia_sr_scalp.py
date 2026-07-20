"""Asia M5 support/resistance scalp — recommended Asia desk strategy.

Why this is the Asia recommendation (PH 7AM–7PM):
  - Gold in Asia usually chops between clear M5 levels, not clean trends
  - Edge: fade Support (buy) / Resistance (sell) on closed M5 rejection
  - Major levels = swing S/R + Asia session range high/low
  - SL beyond the level + ATR pad; TP opposite S/R or ~1.1R scalp
  - Stand aside if ADX wakes up (breakout / London prep risk)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.indicators import adx
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session

SIGNAL_COOLDOWN_SECONDS = 600  # 2× M5 bars between scalps


@dataclass(frozen=True)
class Zone:
    kind: str  # "resistance" | "support"
    top: float
    bottom: float
    mid: float
    strength: float
    bar_index: int
    source: str  # "swing" | "session_range"


class AsiaSrScalpStrategy(Strategy):
    """Recommended Asia strategy: M5 Support / Resistance fade scalp."""

    name = "asia_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        swing_lookback: int = 3,
        zone_lookback: int = 36,
        range_lookback: int = 24,
        atr_period: int = 14,
        adx_period: int = 14,
        max_adx: float = 24.0,
        zone_atr_width: float = 0.30,
        touch_atr: float = 0.22,
        sl_pad_atr: float = 0.25,
        reward_r: float = 1.1,
        min_zone_age: int = 2,
        max_zones: int = 8,
        news_filter: bool = True,
        asia_only: bool = True,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(zone_lookback, range_lookback, atr_period * 2) + 40)
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
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []
        self.last_zones: list[dict] = []
        self.last_range: dict | None = None
        self.last_session_label: str | None = None

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

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
                strength=2.4,
                bar_index=n - 2,
                source="session_range",
            ),
            Zone(
                kind="support",
                top=lo + half_w,
                bottom=lo - half_w * 0.2,
                mid=lo,
                strength=2.4,
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
                return resists[0].bottom - 0.1 * atr
        else:
            supports = sorted(
                (z for z in zones if z.kind == "support" and z.top < entry),
                key=lambda z: z.top,
                reverse=True,
            )
            if supports:
                return supports[0].top + 0.1 * atr
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        need = max(self.zone_lookback, self.range_lookback) + self.atr_period + 5
        if len(candles) < need:
            self.last_block_reason = f"Waiting for {need} M5 bars"
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
        asia_ok = session.tier == SessionTier.ASIA if self.asia_only else True
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

        vol = true_atr(candles, self.atr_period)
        strength = adx([c.close for c in candles], self.adx_period)
        if vol is None or strength is None:
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None

        if not gate(
            "ranging_ok",
            strength <= self.max_adx,
            f"ADX={strength:.1f} (max {self.max_adx} for Asia S/R scalp)",
        ):
            self.last_block_reason = "ADX rising — Asia breakout risk, no S/R fade"
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

        bar = candles[-1]
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
            "Rejection candle at support/resistance",
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
        tf = f"M{max(1, bar.period_seconds // 60)}"
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, 0.5 + 0.15 * zone.strength), 3),
            reason=(
                f"{tf} Asia S/R scalp {side.value}: "
                f"{zone.kind} ({zone.source}) {zone.bottom:.2f}-{zone.top:.2f} · "
                f"reject confirm · ADX={strength:.1f} · "
                f"SL beyond level · TP opp S/R or {self.reward_r}R · R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
