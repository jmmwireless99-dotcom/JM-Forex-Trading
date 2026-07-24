"""Smart Money Concepts scalp: liquidity sweep + MSS/ChoCH + FVG/OB retest (M5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


@dataclass
class Zone:
    kind: str  # ASIAN_HIGH / ASIAN_LOW / PDH / PDL / FVG / ORDER_BLOCK
    high: float
    low: float
    swept: bool = False
    side_bias: str | None = None  # BUY after low sweep, SELL after high sweep


@dataclass
class SweepMemory:
    bias: str
    label: str
    level: float
    swept_at: datetime
    session_day: date


def _swing_high(bars: list[Candle], i: int, left: int = 2, right: int = 2) -> bool:
    if i < left or i + right >= len(bars):
        return False
    h = bars[i].high
    return all(h > bars[i - j].high for j in range(1, left + 1)) and all(
        h >= bars[i + j].high for j in range(1, right + 1)
    )


def _swing_low(bars: list[Candle], i: int, left: int = 2, right: int = 2) -> bool:
    if i < left or i + right >= len(bars):
        return False
    lo = bars[i].low
    return all(lo < bars[i - j].low for j in range(1, left + 1)) and all(
        lo <= bars[i + j].low for j in range(1, right + 1)
    )


def _asia_window_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    """Candles in today's Asia box UTC 00:00–06:00 (same as London Judas)."""
    utc = now.astimezone(timezone.utc)
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=6)
    # Before Asia box closes, use prior day's completed Asia range.
    if utc.hour < 6:
        start = start - timedelta(days=1)
        end = start + timedelta(hours=6)
    return [c for c in bars if start <= c.timestamp.astimezone(timezone.utc) < end]


def _prev_day_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    utc = now.astimezone(timezone.utc)
    day0 = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_prev = day0 - timedelta(days=1)
    return [c for c in bars if day_prev <= c.timestamp.astimezone(timezone.utc) < day0]


def _find_fvg(bars: list[Candle]) -> Zone | None:
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.high < c.low:
        return Zone("FVG", high=c.low, low=a.high, side_bias="BUY")
    if a.low > c.high:
        return Zone("FVG", high=a.low, low=c.high, side_bias="SELL")
    return None


def _find_recent_fvg(bars: list[Candle], bias: str, *, lookback: int = 12) -> Zone | None:
    if len(bars) < 3:
        return None
    start = max(3, len(bars) - lookback)
    best: Zone | None = None
    for end in range(start, len(bars) + 1):
        fvg = _find_fvg(bars[:end])
        if fvg is not None and (fvg.side_bias is None or fvg.side_bias == bias):
            best = fvg
    return best


def _find_order_block(bars: list[Candle], bias: str) -> Zone | None:
    if len(bars) < 6:
        return None
    window = bars[-8:-1]
    if bias == "BUY":
        for c in reversed(window):
            if c.close < c.open:
                return Zone("ORDER_BLOCK", high=c.high, low=c.low, side_bias="BUY")
    else:
        for c in reversed(window):
            if c.close > c.open:
                return Zone("ORDER_BLOCK", high=c.high, low=c.low, side_bias="SELL")
    return None


class LiquiditySweepSmcStrategy(Strategy):
    name = "Liquidity_Sweep_SMC"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        news_filter: bool | None = None,
        session_filter: bool | None = None,
        require_sweep: bool = True,
        require_zone_retest: bool = True,
        reward_r: float = 1.8,
        min_stop_atr: float = 1.1,
        min_tp_atr: float = 2.0,
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.require_sweep = require_sweep
        self.require_zone_retest = require_zone_retest
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []
        self._sweep: SweepMemory | None = None
        self._fired_keys: set[str] = set()

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _liquidity_zones(
        self, bars: list[Candle], now: datetime
    ) -> tuple[list[Zone], list[Candle], list[Candle]]:
        asia = _asia_window_bars(bars, now)
        prev_day = _prev_day_bars(bars, now)
        zones: list[Zone] = []
        if asia:
            hi = max(c.high for c in asia)
            lo = min(c.low for c in asia)
            zones.append(Zone("ASIAN_HIGH", high=hi, low=hi))
            zones.append(Zone("ASIAN_LOW", high=lo, low=lo))
        if prev_day:
            hi = max(c.high for c in prev_day)
            lo = min(c.low for c in prev_day)
            zones.append(Zone("PDH", high=hi, low=hi))
            zones.append(Zone("PDL", high=lo, low=lo))
        # Recent swing pool — critical when price already left the Asia box
        recent = bars[-30:] if len(bars) >= 10 else bars
        if len(recent) >= 8:
            # Exclude forming extremes of last 2 bars so a sweep can print against them
            body = recent[:-2]
            r_hi = max(c.high for c in body)
            r_lo = min(c.low for c in body)
            zones.append(Zone("SWING_HIGH", high=r_hi, low=r_hi))
            zones.append(Zone("SWING_LOW", high=r_lo, low=r_lo))
        return zones, asia, prev_day

    def _scan_sweep_on_bar(
        self, bar: Candle, zones: list[Zone], pad: float, day: date
    ) -> SweepMemory | None:
        for z in zones:
            if z.kind in {"ASIAN_HIGH", "PDH", "SWING_HIGH"}:
                if bar.high > z.high + pad and bar.close < z.high:
                    z.swept = True
                    return SweepMemory("SELL", f"{z.kind} sweep", z.high, bar.timestamp, day)
            if z.kind in {"ASIAN_LOW", "PDL", "SWING_LOW"}:
                if bar.low < z.low - pad and bar.close > z.low:
                    z.swept = True
                    return SweepMemory("BUY", f"{z.kind} sweep", z.low, bar.timestamp, day)
        return None

    def _refresh_sweep(
        self, bars: list[Candle], zones: list[Zone], pad: float, day: date
    ) -> None:
        if self._sweep is not None and self._sweep.session_day != day:
            self._sweep = None
        newest: SweepMemory | None = None
        for bar in bars[-24:]:
            ev = self._scan_sweep_on_bar(bar, zones, pad, day)
            if ev is not None:
                newest = ev
        if newest is not None:
            self._sweep = newest

    def _mss_bias(self, bars: list[Candle]) -> str | None:
        if len(bars) < 10:
            return None
        recent = bars[-20:]
        cur = recent[-1]
        swing_highs = [recent[i].high for i in range(len(recent)) if _swing_high(recent, i)]
        swing_lows = [recent[i].low for i in range(len(recent)) if _swing_low(recent, i)]
        buy = bool(
            swing_highs
            and cur.close > max(swing_highs[-2:] if len(swing_highs) >= 2 else swing_highs)
        )
        sell = bool(
            swing_lows
            and cur.close < min(swing_lows[-2:] if len(swing_lows) >= 2 else swing_lows)
        )
        if buy and not sell:
            return "BUY"
        if sell and not buy:
            return "SELL"
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None
        self.last_zones = []

        if len(bars) < 40:
            self.last_block_reason = "Need 40+ M5 bars for SMC"
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

        atr = true_atr(bars, 14)
        if atr is None or atr <= 0:
            self.last_block_reason = "ATR warming up"
            return None

        now = tick.timestamp
        day = now.astimezone(timezone.utc).date()
        zones, asia, prev_day = self._liquidity_zones(bars, now)
        if not zones:
            self.last_block_reason = "No Asia/PDH-PDL liquidity levels yet"
            return None

        cur = bars[-1]
        pad = max(0.08 * atr, 0.15)
        self._refresh_sweep(bars, zones, pad, day)
        sweep = self._sweep

        mss_bias = self._mss_bias(bars)
        bias = (sweep.bias if sweep else None) or mss_bias

        fvg = _find_recent_fvg(bars, bias or "BUY", lookback=12) if bias else _find_fvg(bars)
        if fvg:
            zones.append(fvg)
        ob = _find_order_block(bars, bias or "BUY")
        if ob:
            zones.append(ob)

        self.last_zones = [
            {
                "zone_type": z.kind,
                "price_high": round(z.high, 2),
                "price_low": round(z.low, 2),
                "is_swept": z.swept or (bool(sweep) and z.kind in sweep.label),
            }
            for z in zones
        ]

        self.last_checklist = [
            f"asia_bars={len(asia)} prev_day={len(prev_day)} zones={len(zones)}",
            f"sweep={sweep.label if sweep else 'none'} mss={mss_bias}",
            f"ATR={atr:.2f} pad={pad:.2f}",
        ]

        if self.require_sweep and sweep is None:
            self.last_block_reason = "Waiting for Asia/PDH/swing liquidity sweep"
            return None
        if bias is None:
            self.last_block_reason = "Sweep locked — waiting MSS"
            return None

        # Require real FVG/OB retest — no synthetic current-candle OB
        entry_zone = None
        for z in zones:
            if z.kind not in {"FVG", "ORDER_BLOCK"}:
                continue
            if z.side_bias and z.side_bias != bias:
                continue
            if z.low - pad <= cur.close <= z.high + pad:
                entry_zone = z
                break
            if bias == "BUY" and cur.low <= z.high and cur.close >= z.low:
                entry_zone = z
                break
            if bias == "SELL" and cur.high >= z.low and cur.close <= z.high:
                entry_zone = z
                break

        if entry_zone is None:
            self.last_block_reason = (
                f"Sweep ok ({sweep.label if sweep else 'structure'}) — waiting FVG/OB retest"
            )
            return None
        if self.require_zone_retest and entry_zone.kind not in {"FVG", "ORDER_BLOCK"}:
            self.last_block_reason = "Waiting FVG/OB retest"
            return None

        key = f"{bias}-{day}-{round(entry_zone.low, 1)}-{round(entry_zone.high, 1)}"
        if key in self._fired_keys:
            self.last_block_reason = "Already taken this SMC zone today"
            return None
        self._fired_keys.add(key)

        side = Side.BUY if bias == "BUY" else Side.SELL
        reason = (
            f"SMC {side.value} · {sweep.label} · "
            f"{'MSS' if mss_bias else 'sweep-bias'} · {entry_zone.kind} entry"
        )
        self.last_checklist.append(
            f"entry={entry_zone.kind} {entry_zone.low:.2f}-{entry_zone.high:.2f}"
        )

        levels = structure_levels(
            side,
            entry=tick.ask if side == Side.BUY else tick.bid,
            candles=bars,
            atr=atr,
            reward_r=self.reward_r,
            min_stop_atr=self.min_stop_atr,
            min_tp_atr=self.min_tp_atr,
        )
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.9,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
