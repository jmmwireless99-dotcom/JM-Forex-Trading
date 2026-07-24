"""London session clocks + Asian range calculator for Judas Swing setups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from app.models.domain import Candle

# Spec pip for London desk: 1 pip = $0.01 on XAUUSD (user: 30 pips = $0.30)
LONDON_PIP = 0.01

ASIA_START_UTC = time(0, 0)
ASIA_END_UTC = time(6, 0)  # exclusive → 00:00–06:00
LONDON_OPEN_UTC = time(7, 0)
LONDON_SWEEP_END_UTC = time(9, 0)  # primary sweep window 07–09
LONDON_ENTRY_END_UTC = time(11, 0)  # expansion / entry until 11:00
PENDING_KILL_UTC = time(12, 0)  # cancel unfilled limits


@dataclass(frozen=True)
class AsianRange:
    session_date: date
    high: float
    low: float
    range_pips: float
    bar_count: int

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0


def utc_day(ts: datetime) -> date:
    return ts.astimezone(timezone.utc).date()


def _combine(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=timezone.utc)


def asian_window(session_date: date) -> tuple[datetime, datetime]:
    start = _combine(session_date, ASIA_START_UTC)
    end = _combine(session_date, ASIA_END_UTC)
    return start, end


def is_london_entry_window(ts: datetime) -> bool:
    """07:00–11:00 UTC — high-volatility London expansion."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return False
    t = utc.timetz().replace(tzinfo=None)
    return LONDON_OPEN_UTC <= t < LONDON_ENTRY_END_UTC


def is_london_sweep_window(ts: datetime) -> bool:
    """07:00–09:00 UTC — Judas sweep hunt window."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return False
    t = utc.timetz().replace(tzinfo=None)
    return LONDON_OPEN_UTC <= t < LONDON_SWEEP_END_UTC


def is_past_pending_kill(ts: datetime) -> bool:
    utc = ts.astimezone(timezone.utc)
    t = utc.timetz().replace(tzinfo=None)
    return t >= PENDING_KILL_UTC


def pending_expire_at(ts: datetime) -> datetime:
    """Hard kill for unfilled limits: 12:00 UTC same day."""
    d = utc_day(ts)
    return _combine(d, PENDING_KILL_UTC)


def ph_label(ts: datetime) -> str:
    """PH = UTC+8 → London 07–16 UTC ≈ 15:00–00:00 PH."""
    utc = ts.astimezone(timezone.utc)
    ph = utc + timedelta(hours=8)
    return ph.strftime("%Y-%m-%d %H:%M PH")


def calculate_asian_range(
    candles: list[Candle],
    *,
    as_of: datetime | None = None,
) -> AsianRange | None:
    """High/Low of XAUUSD between 00:00–06:00 UTC for the session day."""
    as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    session_date = utc_day(as_of)
    # Before Asia completes, use previous weekday's range for planning
    start, end = asian_window(session_date)
    if as_of < end:
        # Prefer completed prior weekday Asia box
        probe = session_date - timedelta(days=1)
        while probe.weekday() >= 5:
            probe -= timedelta(days=1)
        start, end = asian_window(probe)
        session_date = probe

    bars = [
        c
        for c in candles
        if start <= c.timestamp.astimezone(timezone.utc) < end
        or (c.open_time and start <= c.open_time.astimezone(timezone.utc) < end)
    ]
    if len(bars) < 3:
        return None

    high = max(c.high for c in bars)
    low = min(c.low for c in bars)
    return AsianRange(
        session_date=session_date,
        high=round(high, 2),
        low=round(low, 2),
        range_pips=round((high - low) / LONDON_PIP, 1),
        bar_count=len(bars),
    )


def pips(distance: float) -> float:
    return distance / LONDON_PIP


def price_from_pips(n: float) -> float:
    return n * LONDON_PIP
