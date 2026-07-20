"""Gold S/R supply-demand scalp for XAUUSD on closed M5 candles.

Asia desk / London-NY edge:
  - Map swing highs → supply zones and swing lows → demand zones
  - Enter when price revisits a fresh zone with a rejection candle
  - SL beyond the zone + ATR pad; TP toward opposite S/R or ~1.2R
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import bearish_confirm, bullish_confirm, true_atr
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session

SIGNAL_COOLDOWN_SECONDS = 600  # 2× M5 bars between scalps


@dataclass(frozen=True)
class Zone:
    kind: str  # "supply" | "demand"
    top: float
    bottom: float
    mid: float
    strength: float
    bar_index: int


class GoldSrScalpStrategy(Strategy):
    """Fade revisits of M5 supply/demand zones with rejection confirmation."""

    name = "gold_sr_scalp"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        swing_lookback: int = 3,
        zone_lookback: int = 40,
        atr_period: int = 14,
        zone_atr_width: float = 0.35,
        touch_atr: float = 0.20,
        sl_pad_atr: float = 0.25,
        reward_r: float = 1.2,
        min_zone_age: int = 3,
        max_zones: int = 6,
        session_filter: bool = True,
        news_filter: bool = True,
        news_before_minutes: int = 45,
        news_after_minutes: int = 30,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(zone_lookback, atr_period * 2) + 40)
        self.swing_lookback = swing_lookback
        self.zone_lookback = zone_lookback
        self.atr_period = atr_period
        self.zone_atr_width = zone_atr_width
        self.touch_atr = touch_atr
        self.sl_pad_atr = sl_pad_atr
        self.reward_r = reward_r
        self.min_zone_age = min_zone_age
        self.max_zones = max_zones
        self.session_filter = session_filter
        self.news_filter = news_filter
        self.news_before_minutes = news_before_minutes
        self.news_after_minutes = news_after_minutes
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_checklist: list[dict] = []
        self.last_zones: list[dict] = []
        self.last_session_label: str | None = None

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _detect_zones(self, candles: list[Candle], atr: float) -> list[Zone]:
        """Swing highs → supply, swing lows → demand (most recent first)."""
        n = len(candles)
        lb = self.swing_lookback
        half_w = self.zone_atr_width * atr
        zones: list[Zone] = []
        start = max(lb, n - self.zone_lookback)
        end = n - 1  # exclude forming/last signal bar from swing pivot
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
            strength = 1.0 + min(2.0, age / 20.0)
            if is_high:
                zones.append(
                    Zone(
                        kind="supply",
                        top=hi + half_w * 0.25,
                        bottom=hi - half_w,
                        mid=hi,
                        strength=strength,
                        bar_index=i,
                    )
                )
            if is_low:
                zones.append(
                    Zone(
                        kind="demand",
                        top=lo + half_w,
                        bottom=lo - half_w * 0.25,
                        mid=lo,
                        strength=strength,
                        bar_index=i,
                    )
                )

        # Prefer fresher, stronger zones; drop overlaps of same kind
        zones.sort(key=lambda z: (z.bar_index, z.strength), reverse=True)
        kept: list[Zone] = []
        for z in zones:
            if any(
                k.kind == z.kind and abs(k.mid - z.mid) <= half_w * 1.5 for k in kept
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
            supplies = sorted(
                (z for z in zones if z.kind == "supply" and z.bottom > entry),
                key=lambda z: z.bottom,
            )
            if supplies:
                return supplies[0].bottom - 0.1 * atr
        else:
            demands = sorted(
                (z for z in zones if z.kind == "demand" and z.top < entry),
                key=lambda z: z.top,
                reverse=True,
            )
            if demands:
                return demands[0].top + 0.1 * atr
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        need = self.zone_lookback + self.atr_period + 5
        if len(candles) < need:
            self.last_block_reason = f"Waiting for {need} M5 bars"
            self.last_checklist = []
            self.last_zones = []
            return None

        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        ok_session = True
        if self.session_filter:
            # Asia desk uses this for pullback/S/R; full map uses London/NY tiers.
            ok_session = session.tier in {
                SessionTier.PRIME,
                SessionTier.ALLOWED,
                SessionTier.ASIA,
            }
        if not gate("session", ok_session, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        if self.news_filter:
            news = check_news_blackout(
                tick.timestamp,
                before_minutes=self.news_before_minutes,
                after_minutes=self.news_after_minutes,
            )
            if not gate("news", not news.blocked, news.reason):
                self.last_block_reason = news.reason
                self.last_checklist = checks
                return None

        vol = true_atr(candles, self.atr_period)
        if vol is None:
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None

        zones = self._detect_zones(candles, vol)
        self.last_zones = [
            {
                "kind": z.kind,
                "top": round(z.top, 2),
                "bottom": round(z.bottom, 2),
                "mid": round(z.mid, 2),
                "strength": round(z.strength, 2),
            }
            for z in zones
        ]
        if not gate("zones", bool(zones), f"{len(zones)} active S/R zones"):
            self.last_block_reason = "No swing supply/demand zones"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate("cooldown", cool, f"{self.signal_cooldown_seconds}s between scalps"):
            self.last_block_reason = "Scalp cooldown"
            self.last_checklist = checks
            return None

        bar = candles[-1]
        demand_hits = [
            z for z in zones if z.kind == "demand" and self._touching(bar, z, vol)
        ]
        supply_hits = [
            z for z in zones if z.kind == "supply" and self._touching(bar, z, vol)
        ]
        buy_ok = bool(demand_hits) and bullish_confirm(bar) and bar.close > bar.open
        sell_ok = bool(supply_hits) and bearish_confirm(bar) and bar.close < bar.open

        gate("revisit", bool(demand_hits or supply_hits), "Price revisiting S/R zone")
        gate(
            "reject",
            (bullish_confirm(bar) if demand_hits else False)
            or (bearish_confirm(bar) if supply_hits else False),
            "Rejection candle at zone",
        )
        self.last_checklist = checks

        if not (buy_ok or sell_ok):
            self.last_block_reason = "No S/R revisit + rejection on this M5"
            return None

        # Prefer the nearest touched zone of the winning side
        if buy_ok and sell_ok:
            # Both sides rare — pick closer mid to close
            d = min(demand_hits, key=lambda z: abs(bar.close - z.mid))
            s = min(supply_hits, key=lambda z: abs(bar.close - z.mid))
            if abs(bar.close - d.mid) <= abs(bar.close - s.mid):
                sell_ok = False
            else:
                buy_ok = False

        side = Side.BUY if buy_ok else Side.SELL
        zone = (
            min(demand_hits, key=lambda z: abs(bar.close - z.mid))
            if side == Side.BUY
            else min(supply_hits, key=lambda z: abs(bar.close - z.mid))
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
            strength=round(min(1.0, 0.45 + 0.2 * zone.strength), 3),
            reason=(
                f"{tf} S/R scalp {side.value} [{session.tier.value}]: "
                f"{zone.kind} zone {zone.bottom:.2f}-{zone.top:.2f} · "
                f"reject confirm · SL beyond zone · TP opp/S/R or {self.reward_r}R "
                f"· R={rr:.2f}"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
