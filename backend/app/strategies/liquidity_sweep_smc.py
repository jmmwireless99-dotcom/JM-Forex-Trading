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
    bar_index: int = -1


def _bar_utc(candle: Candle) -> datetime:
    ts = candle.open_time or candle.timestamp
    return ts.astimezone(timezone.utc)


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
    """Candles in today's Asia box UTC 00:00–07:00."""
    utc = now.astimezone(timezone.utc)
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=7)
    if utc.hour < 7:
        start = start - timedelta(days=1)
        end = start + timedelta(hours=7)
    return [c for c in bars if start <= _bar_utc(c) < end]


def _prev_day_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    utc = now.astimezone(timezone.utc)
    day0 = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_prev = day0 - timedelta(days=1)
    return [c for c in bars if day_prev <= _bar_utc(c) < day0]


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


def _wick_swept_high(bar: Candle, level: float, pad: float) -> bool:
    """Wick took liquidity above level with rejection (not a clean breakout)."""
    if bar.high <= level + pad:
        return False
    body_top = max(bar.open, bar.close)
    rng = bar.high - bar.low + 1e-9
    upper_wick = bar.high - body_top
    return body_top <= level + pad * 0.4 or upper_wick / rng >= 0.4


def _wick_swept_low(bar: Candle, level: float, pad: float) -> bool:
    if bar.low >= level - pad:
        return False
    body_bot = min(bar.open, bar.close)
    rng = bar.high - bar.low + 1e-9
    lower_wick = body_bot - bar.low
    return body_bot >= level - pad * 0.4 or lower_wick / rng >= 0.4


def _soft_momentum(bar: Candle, bias: str) -> bool:
    """Directional close without requiring a full engulfing body."""
    rng = bar.high - bar.low + 1e-9
    if bias == "BUY":
        return bar.close >= bar.low + 0.42 * rng
    return bar.close <= bar.high - 0.42 * rng


def _sweep_retest(bar: Candle, sweep: SweepMemory, pad: float) -> bool:
    """Price retested the swept level and rejected in sweep direction."""
    level = sweep.level
    if sweep.bias == "BUY":
        return bar.low <= level + pad and bar.close > level - pad * 0.25
    return bar.high >= level - pad and bar.close < level + pad * 0.25


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
        sweep_lookback_bars: int = 36,
        sweep_valid_bars: int = 18,
        max_trades_per_day: int = 4,
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.require_sweep = require_sweep
        self.sweep_lookback_bars = sweep_lookback_bars
        self.sweep_valid_bars = sweep_valid_bars
        self.max_trades_per_day = max_trades_per_day
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []
        self._sweep: SweepMemory | None = None
        self._fired_keys: set[str] = set()
        self._day_trade_count: dict[date, int] = {}

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
        recent = bars[-30:] if len(bars) >= 10 else bars
        if len(recent) >= 8:
            body = recent[:-2]
            r_hi = max(c.high for c in body)
            r_lo = min(c.low for c in body)
            zones.append(Zone("SWING_HIGH", high=r_hi, low=r_hi))
            zones.append(Zone("SWING_LOW", high=r_lo, low=r_lo))
        return zones, asia, prev_day

    def _scan_sweep_on_bar(
        self,
        bar: Candle,
        zones: list[Zone],
        pad: float,
        day: date,
        *,
        bar_index: int,
    ) -> SweepMemory | None:
        for z in zones:
            if z.kind in {"ASIAN_HIGH", "PDH", "SWING_HIGH"}:
                if _wick_swept_high(bar, z.high, pad):
                    z.swept = True
                    return SweepMemory(
                        "SELL",
                        f"{z.kind} sweep",
                        z.high,
                        _bar_utc(bar),
                        day,
                        bar_index=bar_index,
                    )
            if z.kind in {"ASIAN_LOW", "PDL", "SWING_LOW"}:
                if _wick_swept_low(bar, z.low, pad):
                    z.swept = True
                    return SweepMemory(
                        "BUY",
                        f"{z.kind} sweep",
                        z.low,
                        _bar_utc(bar),
                        day,
                        bar_index=bar_index,
                    )
        return None

    def _refresh_sweep(
        self, bars: list[Candle], zones: list[Zone], pad: float, day: date
    ) -> SweepMemory | None:
        if self._sweep is not None and self._sweep.session_day != day:
            self._sweep = None

        newest: SweepMemory | None = None
        start = max(0, len(bars) - self.sweep_lookback_bars)
        for idx in range(start, len(bars)):
            ev = self._scan_sweep_on_bar(bars[idx], zones, pad, day, bar_index=idx)
            if ev is not None:
                newest = ev

        if newest is not None:
            self._sweep = newest

        sweep = self._sweep
        if sweep is None:
            return None

        age = len(bars) - 1 - sweep.bar_index
        if age > self.sweep_valid_bars:
            self._sweep = None
            return None
        return sweep

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

    def _can_fire(self, key: str, day: date) -> bool:
        count = self._day_trade_count.get(day, 0)
        if count >= self.max_trades_per_day:
            self.last_block_reason = f"Daily cap reached ({self.max_trades_per_day} SMC trades)"
            return False
        if key in self._fired_keys:
            self.last_block_reason = "Already taken this sweep setup"
            return False
        return True

    def _mark_fired(self, key: str, day: date) -> None:
        self._fired_keys.add(key)
        self._day_trade_count[day] = self._day_trade_count.get(day, 0) + 1

    def _build_signal(
        self,
        *,
        bars: list[Candle],
        tick: Tick,
        side: Side,
        bias: str,
        sweep: SweepMemory | None,
        mss_bias: str | None,
        entry_zone: Zone,
        atr: float,
        day: date,
        fire_key: str,
    ) -> Signal:
        reason = (
            f"SMC {side.value} · {sweep.label if sweep else 'structure'} · "
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
            reward_r=1.8,
            min_stop_atr=0.9,
            min_tp_atr=1.8,
            swing_lookback=3,
            atr_pad=0.25,
        )
        self._mark_fired(fire_key, day)
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.9,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
            sweep_price=sweep.level if sweep else None,
        )

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
        cur_idx = len(bars) - 1
        pad = max(0.05 * atr, 0.08)
        sweep = self._refresh_sweep(bars, zones, pad, day)
        sweep_now = self._scan_sweep_on_bar(cur, zones, pad, day, bar_index=cur_idx)

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
                "is_swept": z.swept or (bool(sweep) and z.kind in (sweep.label if sweep else "")),
            }
            for z in zones
        ]

        self.last_checklist = [
            f"asia_bars={len(asia)} prev_day={len(prev_day)} zones={len(zones)}",
            f"sweep={sweep.label if sweep else 'none'} fresh={sweep_now is not None} mss={mss_bias}",
            f"ATR={atr:.2f} pad={pad:.2f}",
        ]

        if self.require_sweep and sweep is None:
            self.last_block_reason = "Waiting for Asia/PDH/swing liquidity sweep"
            return None
        if bias is None:
            self.last_block_reason = "Sweep locked — waiting MSS"
            return None

        side = Side.BUY if bias == "BUY" else Side.SELL

        # 1) Immediate entry on the sweep rejection candle
        if sweep_now is not None and sweep_now.bias == bias:
            fire_key = f"{day}:{sweep_now.label}:{round(sweep_now.level, 1)}:{cur_idx}"
            if self._can_fire(fire_key, day):
                entry_zone = Zone(
                    "SWEEP",
                    high=cur.high,
                    low=cur.low,
                    side_bias=bias,
                )
                return self._build_signal(
                    bars=bars,
                    tick=tick,
                    side=side,
                    bias=bias,
                    sweep=sweep_now,
                    mss_bias=mss_bias,
                    entry_zone=entry_zone,
                    atr=atr,
                    day=day,
                    fire_key=fire_key,
                )

        # 2) Retest of swept level within validity window
        if sweep is not None and _sweep_retest(cur, sweep, pad):
            fire_key = f"{day}:retest:{sweep.label}:{round(sweep.level, 1)}:{cur_idx}"
            if self._can_fire(fire_key, day):
                entry_zone = Zone("RETEST", high=cur.high, low=cur.low, side_bias=bias)
                return self._build_signal(
                    bars=bars,
                    tick=tick,
                    side=side,
                    bias=bias,
                    sweep=sweep,
                    mss_bias=mss_bias,
                    entry_zone=entry_zone,
                    atr=atr,
                    day=day,
                    fire_key=fire_key,
                )

        # 3) FVG / OB retest
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

        # 4) Soft momentum after sweep (no full engulfing required)
        if entry_zone is None:
            if _soft_momentum(cur, bias) and (mss_bias == bias or sweep is not None):
                entry_zone = Zone(
                    "ORDER_BLOCK",
                    high=cur.high,
                    low=cur.low,
                    side_bias=bias,
                )
            else:
                self.last_block_reason = (
                    f"Sweep ok ({sweep.label if sweep else 'structure'}) — "
                    "waiting retest/FVG/OB/momentum"
                )
                return None

        fire_key = (
            f"{day}:{entry_zone.kind}:{round(entry_zone.low, 1)}:"
            f"{round(entry_zone.high, 1)}:{cur_idx}"
        )
        if not self._can_fire(fire_key, day):
            return None

        return self._build_signal(
            bars=bars,
            tick=tick,
            side=side,
            bias=bias,
            sweep=sweep,
            mss_bias=mss_bias,
            entry_zone=entry_zone,
            atr=atr,
            day=day,
            fire_key=fire_key,
        )
