"""Smart Money Concepts: liquidity sweep + displacement + MSS/ChoCH + FVG50 retest.

Mechanical blueprint (XAUUSD):
  1) Kill zones — London / NY volume only (session map + optional filter)
  2) Mark PDH/PDL (+ Asia H/L, swings as secondary liquidity)
  3) Wait for sweep (fake breakout wick → close back inside)
  4) M5 displacement + MSS/ChoCH confirm
  5) LIMIT at FVG 50% (or OB retest) · SL beyond sweep · TP opposite liq / ≥2.5R
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.models.domain import Candle, OrderType, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


@dataclass
class Zone:
    kind: str  # ASIAN_HIGH / ASIAN_LOW / PDH / PDL / FVG / ORDER_BLOCK / SWING_*
    high: float
    low: float
    swept: bool = False
    side_bias: str | None = None  # BUY after low sweep, SELL after high sweep


@dataclass
class SweepMemory:
    bias: str
    label: str
    level: float
    extreme: float  # wick tip that grabbed liquidity
    swept_at: datetime
    session_day: date
    bar_index: int


# Preferred liquidity order — PDH/PDL first (user blueprint), then Asia, then swings.
_HIGH_LIQ = ("PDH", "ASIAN_HIGH", "SWING_HIGH")
_LOW_LIQ = ("PDL", "ASIAN_LOW", "SWING_LOW")


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
    """Candles in today's Asia box UTC 00:00–06:00."""
    utc = now.astimezone(timezone.utc)
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=6)
    if utc.hour < 6:
        # Use last completed weekday Asia box (skip empty Sunday).
        start = start - timedelta(days=1)
        while start.weekday() >= 5:
            start = start - timedelta(days=1)
        end = start + timedelta(hours=6)
    return [c for c in bars if start <= c.timestamp.astimezone(timezone.utc) < end]


def _prev_day_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    """Previous trading day OHLC pool for PDH/PDL (skip weekend empty days)."""
    utc = now.astimezone(timezone.utc)
    day0 = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_prev = day0 - timedelta(days=1)
    while day_prev.weekday() >= 5:
        day_prev = day_prev - timedelta(days=1)
    day_end = day_prev + timedelta(days=1)
    # If Friday→Monday, prev day is Friday.
    return [
        c
        for c in bars
        if day_prev <= c.timestamp.astimezone(timezone.utc) < day_end
    ]


def _find_fvg(bars: list[Candle]) -> Zone | None:
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.high < c.low:
        return Zone("FVG", high=c.low, low=a.high, side_bias="BUY")
    if a.low > c.high:
        return Zone("FVG", high=a.low, low=c.high, side_bias="SELL")
    return None


def _find_recent_fvg(
    bars: list[Candle],
    bias: str,
    *,
    lookback: int = 14,
    after_ts: datetime | None = None,
) -> Zone | None:
    if len(bars) < 3:
        return None
    start = max(3, len(bars) - lookback)
    best: Zone | None = None
    for end in range(start, len(bars) + 1):
        window = bars[:end]
        if after_ts is not None and window[-1].timestamp < after_ts:
            continue
        fvg = _find_fvg(window)
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


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def _has_displacement(
    bars: list[Candle],
    *,
    bias: str,
    after_ts: datetime,
    atr: float,
    min_atr: float,
) -> bool:
    """Strong impulse candle after the sweep (ChoCH fuel)."""
    need = max(min_atr * atr, 0.8)
    for c in bars:
        if c.timestamp <= after_ts:
            continue
        if _body(c) < need:
            continue
        rng = c.high - c.low + 1e-9
        if _body(c) / rng < 0.55:
            continue
        if bias == "BUY" and c.close > c.open:
            return True
        if bias == "SELL" and c.close < c.open:
            return True
    return False


def _smc_expire_at(ts: datetime) -> datetime:
    """Cancel unfilled FVG50 limits after 2 hours."""
    return ts.astimezone(timezone.utc) + timedelta(hours=2)


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
        require_displacement: bool = True,
        prefer_pdh_pdl: bool = True,
        use_limit_entry: bool = True,
        fvg_entry_pct: float = 0.50,
        reward_r: float = 2.8,
        min_stop_atr: float = 1.4,
        min_tp_atr: float = 3.0,
        max_stop_atr: float = 3.2,
        min_sweep_atr: float = 0.35,
        max_sweep_atr: float = 2.8,
        min_displacement_atr: float = 0.55,
        sl_buffer_atr: float = 0.40,
        min_sl_dollars: float = 1.50,
        sweep_max_age_bars: int = 18,
        mt_near_limit_pips: float = 120.0,
        max_entries_per_day: int = 0,
        # Kill zones UTC (inclusive start, exclusive end) — blueprint PH London/NY.
        kill_zones_utc: tuple[tuple[int, int], ...] = ((7, 11), (13, 16)),
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.require_sweep = require_sweep
        self.require_zone_retest = require_zone_retest
        self.require_displacement = require_displacement
        self.prefer_pdh_pdl = prefer_pdh_pdl
        self.use_limit_entry = use_limit_entry
        self.fvg_entry_pct = min(max(float(fvg_entry_pct), 0.35), 0.65)
        self.reward_r = reward_r
        self.min_stop_atr = min_stop_atr
        self.min_tp_atr = min_tp_atr
        self.max_stop_atr = max_stop_atr
        self.min_sweep_atr = min_sweep_atr
        self.max_sweep_atr = max_sweep_atr
        self.min_displacement_atr = min_displacement_atr
        self.sl_buffer_atr = sl_buffer_atr
        self.min_sl_dollars = min_sl_dollars
        self.sweep_max_age_bars = max(6, int(sweep_max_age_bars))
        self.mt_near_limit_pips = float(mt_near_limit_pips)
        self.kill_zones_utc = kill_zones_utc
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []
        self._sweep: SweepMemory | None = None
        self._fired_keys: set[str] = set()
        # 0 = unlimited — quality gates only.
        self.max_entries_per_day = max(0, int(max_entries_per_day))
        self._entries_today: dict[date, int] = {}

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _in_kill_zone(self, ts: datetime) -> bool:
        hour = ts.astimezone(timezone.utc).hour
        return any(start <= hour < end for start, end in self.kill_zones_utc)

    def _liquidity_zones(
        self, bars: list[Candle], now: datetime
    ) -> tuple[list[Zone], list[Candle], list[Candle]]:
        asia = _asia_window_bars(bars, now)
        prev_day = _prev_day_bars(bars, now)
        zones: list[Zone] = []
        # PDH/PDL first when prefer_pdh_pdl — scan order uses kind priority too.
        if prev_day:
            hi = max(c.high for c in prev_day)
            lo = min(c.low for c in prev_day)
            zones.append(Zone("PDH", high=hi, low=hi))
            zones.append(Zone("PDL", high=lo, low=lo))
        if asia:
            hi = max(c.high for c in asia)
            lo = min(c.low for c in asia)
            zones.append(Zone("ASIAN_HIGH", high=hi, low=hi))
            zones.append(Zone("ASIAN_LOW", high=lo, low=lo))
        recent = bars[-30:] if len(bars) >= 10 else bars
        if len(recent) >= 8:
            body = recent[:-2]
            r_hi = max(c.high for c in body)
            r_lo = min(c.low for c in body)
            zones.append(Zone("SWING_HIGH", high=r_hi, low=r_hi))
            zones.append(Zone("SWING_LOW", high=r_lo, low=r_lo))
        return zones, asia, prev_day

    def _zone_priority(self, kind: str) -> int:
        if not self.prefer_pdh_pdl:
            return 0
        order = {
            "PDH": 0,
            "PDL": 0,
            "ASIAN_HIGH": 1,
            "ASIAN_LOW": 1,
            "SWING_HIGH": 2,
            "SWING_LOW": 2,
        }
        return order.get(kind, 9)

    def _scan_sweep_on_bar(
        self,
        bar: Candle,
        bar_index: int,
        zones: list[Zone],
        pad: float,
        atr: float,
        day: date,
    ) -> SweepMemory | None:
        ranked = sorted(zones, key=lambda z: self._zone_priority(z.kind))
        for z in ranked:
            if z.kind in _HIGH_LIQ:
                depth = bar.high - z.high
                if depth > pad and bar.close < z.high:
                    if depth < self.min_sweep_atr * atr:
                        continue
                    if depth > self.max_sweep_atr * atr:
                        continue
                    z.swept = True
                    return SweepMemory(
                        "SELL",
                        f"{z.kind} sweep",
                        z.high,
                        bar.high,
                        bar.timestamp,
                        day,
                        bar_index,
                    )
            if z.kind in _LOW_LIQ:
                depth = z.low - bar.low
                if depth > pad and bar.close > z.low:
                    if depth < self.min_sweep_atr * atr:
                        continue
                    if depth > self.max_sweep_atr * atr:
                        continue
                    z.swept = True
                    return SweepMemory(
                        "BUY",
                        f"{z.kind} sweep",
                        z.low,
                        bar.low,
                        bar.timestamp,
                        day,
                        bar_index,
                    )
        return None

    def _refresh_sweep(
        self, bars: list[Candle], zones: list[Zone], pad: float, atr: float, day: date
    ) -> None:
        if self._sweep is not None and self._sweep.session_day != day:
            self._sweep = None
        newest: SweepMemory | None = None
        start = max(0, len(bars) - 24)
        for i in range(start, len(bars)):
            ev = self._scan_sweep_on_bar(bars[i], i, zones, pad, atr, day)
            if ev is not None:
                newest = ev
        if newest is not None:
            self._sweep = newest
        # Expire stale sweeps — no chasing hours-old liquidity grabs.
        if self._sweep is not None:
            age = len(bars) - 1 - self._sweep.bar_index
            if age > self.sweep_max_age_bars:
                self._sweep = None

    def _mss_bias(self, bars: list[Candle], *, after_ts: datetime | None) -> str | None:
        if len(bars) < 10:
            return None
        recent = bars[-20:]
        if after_ts is not None:
            recent = [c for c in recent if c.timestamp >= after_ts] or recent[-8:]
        if len(recent) < 6:
            return None
        cur = recent[-1]
        swing_highs = [
            recent[i].high for i in range(len(recent)) if _swing_high(recent, i)
        ]
        swing_lows = [
            recent[i].low for i in range(len(recent)) if _swing_low(recent, i)
        ]
        buy = bool(
            swing_highs
            and cur.close
            > max(swing_highs[-2:] if len(swing_highs) >= 2 else swing_highs)
        )
        sell = bool(
            swing_lows
            and cur.close
            < min(swing_lows[-2:] if len(swing_lows) >= 2 else swing_lows)
        )
        if buy and not sell:
            return "BUY"
        if sell and not buy:
            return "SELL"
        return None

    def _opposite_liquidity_tp(
        self, bias: str, zones: list[Zone], entry: float, risk: float
    ) -> float | None:
        """Target opposite major high/low when it clears min R."""
        min_r = max(2.0, self.reward_r * 0.85)
        if bias == "BUY":
            targets = sorted(
                (
                    z.high
                    for z in zones
                    if z.kind in {"PDH", "ASIAN_HIGH", "SWING_HIGH"} and z.high > entry
                ),
                reverse=False,
            )
            for t in targets:
                if (t - entry) >= min_r * risk:
                    return round(t, 2)
        else:
            targets = sorted(
                (
                    z.low
                    for z in zones
                    if z.kind in {"PDL", "ASIAN_LOW", "SWING_LOW"} and z.low < entry
                ),
                reverse=True,
            )
            for t in targets:
                if (entry - t) >= min_r * risk:
                    return round(t, 2)
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
            if not self._in_kill_zone(tick.timestamp):
                self.last_block_reason = (
                    "SMC kill zones only — London UTC 07–11 / NY overlap UTC 13–16"
                )
                return None

        atr = true_atr(bars, 14)
        if atr is None or atr <= 0:
            self.last_block_reason = "ATR warming up"
            return None

        now = tick.timestamp
        day = now.astimezone(timezone.utc).date()
        zones, asia, prev_day = self._liquidity_zones(bars, now)
        if not zones:
            self.last_block_reason = "No PDH/PDL / Asia liquidity levels yet"
            return None

        cur = bars[-1]
        pad = max(0.08 * atr, 0.15)
        self._refresh_sweep(bars, zones, pad, atr, day)
        sweep = self._sweep

        after_ts = sweep.swept_at if sweep else None
        mss_bias = self._mss_bias(bars, after_ts=after_ts)
        bias = (sweep.bias if sweep else None) or mss_bias

        fvg = (
            _find_recent_fvg(bars, bias or "BUY", lookback=14, after_ts=after_ts)
            if bias
            else _find_fvg(bars)
        )
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
            f"sweep={sweep.label if sweep else 'none'} mss={mss_bias}",
            f"ATR={atr:.2f} pad={pad:.2f} kill_zone={self._in_kill_zone(now)}",
        ]

        if self.require_sweep and sweep is None:
            self.last_block_reason = "Waiting for PDH/PDL/Asia/swing liquidity sweep"
            return None
        if sweep is not None and mss_bias is None:
            self.last_block_reason = "Sweep locked — waiting MSS/ChoCH confirm"
            return None
        if sweep is not None and mss_bias is not None and mss_bias != sweep.bias:
            self.last_block_reason = (
                f"Sweep {sweep.bias} vs MSS {mss_bias} conflict — no entry"
            )
            return None
        bias = (sweep.bias if sweep else None) or mss_bias
        if bias is None:
            self.last_block_reason = "No sweep/MSS bias"
            return None

        if self.require_displacement and sweep is not None:
            if not _has_displacement(
                bars,
                bias=bias,
                after_ts=sweep.swept_at,
                atr=atr,
                min_atr=self.min_displacement_atr,
            ):
                self.last_block_reason = (
                    "Sweep+MSS ok — waiting displacement candle after sweep"
                )
                return None

        if (
            self.max_entries_per_day > 0
            and self._entries_today.get(day, 0) >= self.max_entries_per_day
        ):
            self.last_block_reason = (
                f"SMC daily cap reached ({self.max_entries_per_day})"
            )
            return None

        # Prefer FVG; OB is backup retest.
        entry_zone = None
        for prefer in ("FVG", "ORDER_BLOCK"):
            for z in zones:
                if z.kind != prefer:
                    continue
                if z.side_bias and z.side_bias != bias:
                    continue
                entry_zone = z
                break
            if entry_zone is not None:
                break

        if entry_zone is None:
            self.last_block_reason = (
                f"Sweep ok ({sweep.label if sweep else 'structure'}) — waiting FVG/OB"
            )
            return None
        if self.require_zone_retest and entry_zone.kind not in {"FVG", "ORDER_BLOCK"}:
            self.last_block_reason = "Waiting FVG/OB zone"
            return None

        # FVG 50% equilibrium (blueprint) — mid of imbalance.
        span = entry_zone.high - entry_zone.low
        if span <= 0:
            self.last_block_reason = "Invalid entry zone width"
            return None
        if bias == "BUY":
            limit_px = round(entry_zone.low + self.fvg_entry_pct * span, 2)
        else:
            limit_px = round(entry_zone.high - self.fvg_entry_pct * span, 2)

        mid = float(tick.mid)
        # Through equilibrium this bar → MARKET; else LIMIT pullback to FVG50.
        through_eq = (
            bias == "BUY" and cur.low <= limit_px and cur.close >= limit_px
        ) or (bias == "SELL" and cur.high >= limit_px and cur.close <= limit_px)
        use_limit = bool(
            self.use_limit_entry and entry_zone.kind == "FVG" and not through_eq
        )

        if use_limit:
            # BUY limit needs price above eq; SELL limit needs price below eq.
            if bias == "BUY" and mid <= limit_px:
                use_limit = False
            elif bias == "SELL" and mid >= limit_px:
                use_limit = False
            elif bias == "BUY" and mid > limit_px + 1.5 * atr:
                self.last_block_reason = "Price too far above FVG50 — wait next retest"
                return None
            elif bias == "SELL" and mid < limit_px - 1.5 * atr:
                self.last_block_reason = "Price too far below FVG50 — wait next retest"
                return None

        key = (
            f"{bias}-{day}-{entry_zone.kind}-"
            f"{round(entry_zone.low, 1)}-{round(entry_zone.high, 1)}"
        )
        if key in self._fired_keys:
            self.last_block_reason = "Already taken this SMC zone today"
            return None

        side = Side.BUY if bias == "BUY" else Side.SELL
        entry = limit_px if use_limit else (tick.ask if side == Side.BUY else tick.bid)

        # SL beyond sweep wick + buffer (gold $ — not tiny 15–20 * $0.01 "pips").
        buf = max(self.sl_buffer_atr * atr, self.min_sl_dollars)
        if side == Side.BUY:
            sweep_sl = (sweep.extreme - buf) if sweep else entry_zone.low - buf
            zone_sl = entry_zone.low - buf
            anchor = min(sweep_sl, zone_sl)
        else:
            sweep_sl = (sweep.extreme + buf) if sweep else entry_zone.high + buf
            zone_sl = entry_zone.high + buf
            anchor = max(sweep_sl, zone_sl)

        levels = structure_levels(
            side,
            entry=entry,
            candles=bars,
            atr=atr,
            swing_lookback=8,
            reward_r=self.reward_r,
            min_stop_atr=self.min_stop_atr,
            max_stop_atr=self.max_stop_atr,
            min_tp_atr=self.min_tp_atr,
            anchor_sl=anchor,
        )
        risk = abs(entry - levels.stop_loss)
        if risk <= 0:
            self.last_block_reason = "Invalid SMC risk distance"
            return None

        opp_tp = self._opposite_liquidity_tp(bias, zones, entry, risk)
        take_profit = opp_tp if opp_tp is not None else levels.take_profit

        # Final R gate — never take < 2R setups.
        reward = abs(take_profit - entry)
        if reward / risk < 2.0:
            self.last_block_reason = (
                f"R:R {reward / risk:.2f} < 2.0 — skip thin target"
            )
            return None

        self._fired_keys.add(key)
        self._entries_today[day] = self._entries_today.get(day, 0) + 1

        sweep_label = sweep.label if sweep is not None else "MSS"
        mode = "FVG50 LIMIT" if use_limit else f"{entry_zone.kind} MARKET"
        reason = (
            f"SMC {side.value} · {sweep_label} · displacement+MSS · {mode} "
            f"@ {entry:.2f} · SL {levels.stop_loss} · TP {take_profit}"
        )
        self.last_checklist.append(
            f"entry={mode} {entry_zone.low:.2f}-{entry_zone.high:.2f} "
            f"eq={limit_px:.2f} R={reward / risk:.2f}"
        )

        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.92,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=take_profit,
            order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
            limit_price=limit_px if use_limit else None,
            expire_at=_smc_expire_at(tick.timestamp) if use_limit else None,
            sweep_price=sweep.extreme if sweep else None,
            timestamp=tick.timestamp,
        )
