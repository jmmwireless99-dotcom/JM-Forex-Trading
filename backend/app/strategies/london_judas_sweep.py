"""London Judas Swing & Liquidity Sweep — Asian range trap → FVG limit entry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.models.domain import Candle, OrderType, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.london_session import (
    LONDON_PIP,
    calculate_asian_range,
    is_london_entry_window,
    is_london_sweep_window,
    pending_expire_at,
    price_from_pips,
)
from app.strategies.news_calendar import check_london_news_blackout


@dataclass
class FVG:
    high: float
    low: float
    mid: float
    bias: str  # BUY | SELL


@dataclass
class SweepMemory:
    """Judas sweep remembered for later ChoCH + FVG entry (not same-bar only)."""

    bias: str  # SELL after Asia high, BUY after Asia low
    sweep_price: float
    asia_high: float
    asia_low: float
    session_date: date
    swept_at: datetime
    sweep_pips: float


def _swing_low_broken(bars: list[Candle], lookback: int = 8) -> bool:
    if len(bars) < lookback + 2:
        return False
    window = bars[-(lookback + 1) : -1]
    swing = min(c.low for c in window)
    return bars[-1].close < swing


def _swing_high_broken(bars: list[Candle], lookback: int = 8) -> bool:
    if len(bars) < lookback + 2:
        return False
    window = bars[-(lookback + 1) : -1]
    swing = max(c.high for c in window)
    return bars[-1].close > swing


def find_bearish_fvg(bars: list[Candle]) -> FVG | None:
    """Imbalance: candle1.low > candle3.high → gap mid = 50% equilibrium."""
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.low > c.high:
        hi, lo = a.low, c.high
        return FVG(high=hi, low=lo, mid=round((hi + lo) / 2, 2), bias="SELL")
    return None


def find_bullish_fvg(bars: list[Candle]) -> FVG | None:
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.high < c.low:
        hi, lo = c.low, a.high
        return FVG(high=hi, low=lo, mid=round((hi + lo) / 2, 2), bias="BUY")
    return None


def find_recent_fvg(bars: list[Candle], bias: str, *, lookback: int = 16) -> FVG | None:
    """Most recent FVG of the given bias within the last `lookback` closes."""
    if len(bars) < 3:
        return None
    start = max(3, len(bars) - lookback)
    best: FVG | None = None
    for end in range(start, len(bars) + 1):
        window = bars[:end]
        fvg = find_bearish_fvg(window) if bias == "SELL" else find_bullish_fvg(window)
        if fvg is not None:
            best = fvg
    return best


class LondonJudasSweepStrategy(Strategy):
    """London 07–11 UTC Judas Swing: sweep Asia H/L → ChoCH → FVG 50% limit.

    Sweep is remembered for the session so entry can fire on a later bar once
    ChoCH + FVG form (classic Judas flow — not same-candle only).
    """

    name = "London_Judas_Sweep"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        # pip = $0.01 → 50–350 pips = $0.50–$3.50 (realistic XAUUSD Judas wicks)
        min_sweep_pips: float = 50.0,
        max_sweep_pips: float = 350.0,
        sl_buffer_pips: float = 80.0,
        max_spread_pips: float = 40.0,
        news_filter: bool | None = None,
        reward_r: float = 3.0,
        mt_near_limit_pips: float = 150.0,
    ) -> None:
        from app.core.config import get_settings

        super().__init__(lookback=lookback)
        self.min_sweep_pips = min_sweep_pips
        self.max_sweep_pips = max_sweep_pips
        self.sl_buffer_pips = sl_buffer_pips
        self.mt_near_limit_pips = mt_near_limit_pips
        self.max_spread_pips = max_spread_pips
        self.news_filter = (
            get_settings().news_filter if news_filter is None else news_filter
        )
        self.reward_r = reward_r
        self.last_checklist: list[dict] = []
        self.last_block_reason: str | None = None
        self.last_range: dict | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []
        self._m1_bars: list[Candle] = []
        self._fired_keys: set[str] = set()
        self._sweep: SweepMemory | None = None

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def set_m1_bars(self, candles: list[Candle]) -> None:
        self._m1_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def _reset_session_memory(self, session_date: date) -> None:
        if self._sweep is not None and self._sweep.session_date != session_date:
            self._sweep = None
        # Drop fired keys from other days
        stale = [k for k in self._fired_keys if not k.endswith(str(session_date))]
        for k in stale:
            self._fired_keys.discard(k)

    def _detect_sweep_on_bar(
        self,
        bar: Candle,
        *,
        asia_high: float,
        asia_low: float,
        session_date: date,
        min_sweep: float,
        max_sweep: float,
    ) -> SweepMemory | None:
        """Rejecting wick beyond Asia H/L within configured pip band."""
        if not (
            is_london_sweep_window(bar.timestamp) or is_london_entry_window(bar.timestamp)
        ):
            return None

        sweep_high = bar.high - asia_high
        if min_sweep <= sweep_high <= max_sweep and bar.close <= asia_high:
            return SweepMemory(
                bias="SELL",
                sweep_price=bar.high,
                asia_high=asia_high,
                asia_low=asia_low,
                session_date=session_date,
                swept_at=bar.timestamp,
                sweep_pips=round(sweep_high / LONDON_PIP, 1),
            )

        sweep_low = asia_low - bar.low
        if min_sweep <= sweep_low <= max_sweep and bar.close >= asia_low:
            return SweepMemory(
                bias="BUY",
                sweep_price=bar.low,
                asia_high=asia_high,
                asia_low=asia_low,
                session_date=session_date,
                swept_at=bar.timestamp,
                sweep_pips=round(sweep_low / LONDON_PIP, 1),
            )
        return None

    def _refresh_sweep_memory(
        self,
        bars: list[Candle],
        *,
        asia_high: float,
        asia_low: float,
        session_date: date,
        min_sweep: float,
        max_sweep: float,
    ) -> None:
        """Scan recent London bars; keep newest valid sweep (prefer 07–09)."""
        primary: SweepMemory | None = None
        any_win: SweepMemory | None = None
        for bar in bars[-36:]:  # ~3h of M5
            ev = self._detect_sweep_on_bar(
                bar,
                asia_high=asia_high,
                asia_low=asia_low,
                session_date=session_date,
                min_sweep=min_sweep,
                max_sweep=max_sweep,
            )
            if ev is None:
                continue
            any_win = ev
            if is_london_sweep_window(bar.timestamp):
                primary = ev
        chosen = primary or any_win
        if chosen is None:
            return
        # Keep existing if same bias and later/equal; replace if newer or primary upgrade
        if self._sweep is None:
            self._sweep = chosen
            return
        if self._sweep.session_date != session_date:
            self._sweep = chosen
            return
        if chosen.swept_at >= self._sweep.swept_at:
            self._sweep = chosen

    def _structure_confirm(self, bars: list[Candle], sweep: SweepMemory) -> bool:
        """ChoCH after sweep, or displacement back through Asia mid."""
        post = [c for c in bars if c.timestamp >= sweep.swept_at]
        if len(post) < 2:
            return False
        cur = post[-1]
        mid = (sweep.asia_high + sweep.asia_low) / 2
        if sweep.bias == "SELL":
            # Prefer post-sweep structure; fall back to full series only if thin
            choch = _swing_low_broken(post if len(post) >= 8 else bars)
            # Must reclaim below Asia mid after the high sweep (not just still below high)
            displacement = cur.close <= mid
            return choch or displacement
        choch = _swing_high_broken(post if len(post) >= 8 else bars)
        displacement = cur.close >= mid
        return choch or displacement

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None

        if not is_london_entry_window(tick.timestamp):
            self.last_block_reason = "Outside London entry window (07:00–11:00 UTC)"
            return None

        if self.news_filter:
            news = check_london_news_blackout(tick.timestamp, before_minutes=15)
            if news.blocked:
                self.last_block_reason = news.reason
                return None

        spread = abs(tick.ask - tick.bid)
        spread_pips = spread / LONDON_PIP
        if spread_pips > self.max_spread_pips:
            self.last_block_reason = (
                f"Spread too wide ({spread_pips:.0f} pips > {self.max_spread_pips:.0f})"
            )
            return None

        asian = calculate_asian_range(bars, as_of=tick.timestamp)
        if asian is None and self._m1_bars:
            asian = calculate_asian_range(self._m1_bars, as_of=tick.timestamp)
        if asian is None:
            self.last_block_reason = "Asian range not ready (need 00:00–06:00 UTC bars)"
            return None

        self._reset_session_memory(asian.session_date)

        self.last_range = {
            "date": asian.session_date.isoformat(),
            "high": asian.high,
            "low": asian.low,
            "mid": asian.mid,
            "range_pips": asian.range_pips,
            "adx": None,
        }

        min_sweep = price_from_pips(self.min_sweep_pips)
        max_sweep = price_from_pips(self.max_sweep_pips)
        sl_buf = price_from_pips(self.sl_buffer_pips)

        self._refresh_sweep_memory(
            bars,
            asia_high=asian.high,
            asia_low=asian.low,
            session_date=asian.session_date,
            min_sweep=min_sweep,
            max_sweep=max_sweep,
        )

        sweep = self._sweep
        self.last_zones = [
            {
                "zone_type": "ASIAN_HIGH",
                "price_high": asian.high,
                "price_low": asian.high,
                "is_swept": bool(sweep and sweep.bias == "SELL"),
            },
            {
                "zone_type": "ASIAN_LOW",
                "price_high": asian.low,
                "price_low": asian.low,
                "is_swept": bool(sweep and sweep.bias == "BUY"),
            },
        ]

        if sweep is None:
            self.last_block_reason = (
                f"Waiting Asia H/L sweep ({self.min_sweep_pips:.0f}–"
                f"{self.max_sweep_pips:.0f} pips / "
                f"${self.min_sweep_pips * LONDON_PIP:.2f}–"
                f"${self.max_sweep_pips * LONDON_PIP:.2f})"
            )
            self.last_checklist = [
                {"name": "Asia range", "ok": True, "detail": f"{asian.low}-{asian.high}"},
                {"name": "Judas sweep", "ok": False, "detail": "not yet"},
            ]
            return None

        confirm = self._structure_confirm(bars, sweep)
        fvg = find_recent_fvg(bars, sweep.bias, lookback=16)
        self.last_checklist = [
            {
                "name": f"Asia {'High' if sweep.bias == 'SELL' else 'Low'} sweep",
                "ok": True,
                "detail": f"+{sweep.sweep_pips}p @ {sweep.sweep_price}",
            },
            {
                "name": "ChoCH / displacement",
                "ok": confirm,
                "detail": "M5 after sweep",
            },
            {
                "name": f"{'Bearish' if sweep.bias == 'SELL' else 'Bullish'} FVG",
                "ok": fvg is not None,
                "detail": str(fvg.mid if fvg else "—"),
            },
        ]

        if not confirm:
            self.last_block_reason = (
                f"Sweep locked ({sweep.bias}) — waiting ChoCH/displacement"
            )
            return None
        if fvg is None:
            self.last_block_reason = f"Sweep+structure ok ({sweep.bias}) — waiting FVG"
            return None

        key = f"{sweep.bias}-{asian.session_date}-{round(fvg.mid, 1)}"
        if key in self._fired_keys:
            self.last_block_reason = "Already fired this FVG level today"
            return None

        entry = fvg.mid
        if sweep.bias == "SELL":
            sl = round(sweep.sweep_price + sl_buf, 2)
            # SELL must have SL above entry — reject inverted FVG geometry.
            if sl <= entry:
                self.last_block_reason = (
                    f"Invalid SELL SL geometry (SL {sl} <= entry {entry})"
                )
                return None
            risk = sl - entry
            tp_asia = asian.low
            tp_rrr = round(entry - self.reward_r * risk, 2)
            tp = tp_asia if (entry - tp_asia) >= risk * 0.9 else tp_rrr
            side = Side.SELL
            reason = (
                f"London Judas SELL · AsiaH {asian.high} swept "
                f"→ structure → FVG50 {entry} · SL {sl} · TP {tp}"
            )
        else:
            sl = round(sweep.sweep_price - sl_buf, 2)
            # BUY must have SL below entry — reject inverted FVG geometry.
            if sl >= entry:
                self.last_block_reason = (
                    f"Invalid BUY SL geometry (SL {sl} >= entry {entry})"
                )
                return None
            risk = entry - sl
            tp_asia = asian.high
            tp_rrr = round(entry + self.reward_r * risk, 2)
            tp = tp_asia if (tp_asia - entry) >= risk * 0.9 else tp_rrr
            side = Side.BUY
            reason = (
                f"London Judas BUY · AsiaL {asian.low} swept "
                f"→ structure → FVG50 {entry} · SL {sl} · TP {tp}"
            )

        self._fired_keys.add(key)
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.92,
            reason=reason,
            stop_loss=sl,
            take_profit=tp,
            order_type=OrderType.LIMIT,
            limit_price=entry,
            expire_at=pending_expire_at(tick.timestamp),
            sweep_price=sweep.sweep_price,
            timestamp=tick.timestamp,
        )
