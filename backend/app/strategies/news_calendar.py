from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class NewsImpact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"


@dataclass(frozen=True)
class NewsEvent:
    name: str
    impact: NewsImpact
    # Approximate UTC hour when the print usually hits
    utc_hour: int
    utc_minute: int = 30
    # weekday: 0=Mon … 4=Fri; None = any weekday (rare)
    weekday: int | None = None
    # day_rule helpers
    week_of_month: int | None = None  # 1..5
    day_of_month: int | None = None
    # First Friday = NFP style
    first_weekday_of_month: int | None = None


# High-impact USD events that commonly spike XAUUSD.
# Times are typical US schedule in UTC (EST/EDT shifts ±1h — we use wide buffers).
USD_GOLD_EVENTS: list[NewsEvent] = [
    NewsEvent(
        "Non-Farm Payrolls (NFP)",
        NewsImpact.HIGH,
        utc_hour=12,
        utc_minute=30,
        first_weekday_of_month=4,  # first Friday
    ),
    NewsEvent(
        "CPI (US)",
        NewsImpact.HIGH,
        utc_hour=12,
        utc_minute=30,
        # mid-month-ish; we blackout around typical CPI window using day range in matcher
        day_of_month=None,
        weekday=None,
    ),
    NewsEvent(
        "FOMC Rate Decision",
        NewsImpact.HIGH,
        utc_hour=18,
        utc_minute=0,
        weekday=2,  # usually Wednesday
        week_of_month=None,
    ),
    NewsEvent(
        "Core PCE",
        NewsImpact.HIGH,
        utc_hour=12,
        utc_minute=30,
    ),
    NewsEvent(
        "US GDP / ISM / Jobless proxy window",
        NewsImpact.MEDIUM,
        utc_hour=14,
        utc_minute=0,
    ),
]


@dataclass(frozen=True)
class NewsBlackout:
    blocked: bool
    event: str | None = None
    reason: str = ""
    minutes_to_event: int | None = None


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int | None:
    """Return day-of-month for the n-th weekday (1-based), or None."""
    count = 0
    for day in range(1, 32):
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            break
        if dt.weekday() == weekday:
            count += 1
            if count == n:
                return day
    return None


def _event_occurrences(event: NewsEvent, day: datetime) -> list[datetime]:
    """Possible event timestamps on a given UTC calendar day."""
    day = day.astimezone(timezone.utc)
    y, m, d = day.year, day.month, day.day
    candidates: list[datetime] = []

    if event.first_weekday_of_month is not None:
        target = _nth_weekday(y, m, event.first_weekday_of_month, 1)
        if target == d:
            candidates.append(
                datetime(y, m, d, event.utc_hour, event.utc_minute, tzinfo=timezone.utc)
            )
        return candidates

    if event.weekday is not None and day.weekday() != event.weekday:
        return []

    # FOMC-ish: 2nd or 3rd Wednesday — mark both potential Wednesdays in month
    if event.name.startswith("FOMC"):
        for n in (1, 2, 3, 4):
            target = _nth_weekday(y, m, 2, n)
            if target == d:
                candidates.append(
                    datetime(y, m, d, event.utc_hour, event.utc_minute, tzinfo=timezone.utc)
                )
        return candidates

    # CPI / PCE / generic high-impact USD data: typically 08:30 ET ≈ 12:30 UTC
    # Blackout on likely mid-month data days (10–15) for CPI-named events,
    # and last business week window for PCE-named events.
    if "CPI" in event.name and not (10 <= d <= 15):
        return []
    if "PCE" in event.name and not (20 <= d <= 31):
        return []

    # Medium catch-all: only weekdays
    if day.weekday() >= 5:
        return []

    if event.impact == NewsImpact.MEDIUM:
        # Soft window — only flag near the top of typical US open data hour
        candidates.append(
            datetime(y, m, d, event.utc_hour, event.utc_minute, tzinfo=timezone.utc)
        )
        return candidates

    candidates.append(
        datetime(y, m, d, event.utc_hour, event.utc_minute, tzinfo=timezone.utc)
    )
    return candidates


def check_news_blackout(
    ts: datetime,
    *,
    before_minutes: int = 45,
    after_minutes: int = 30,
    include_medium: bool = False,
) -> NewsBlackout:
    """Return whether we should stand aside around USD/gold news."""
    ts = ts.astimezone(timezone.utc)
    window_days = [ts - timedelta(days=1), ts, ts + timedelta(days=1)]

    nearest: tuple[int, NewsEvent] | None = None
    for day in window_days:
        for event in USD_GOLD_EVENTS:
            if event.impact == NewsImpact.MEDIUM and not include_medium:
                continue
            for when in _event_occurrences(event, day):
                delta_min = int((when - ts).total_seconds() // 60)
                # inside [-before, +after]
                if -before_minutes <= delta_min <= after_minutes:
                    abs_delta = abs(delta_min)
                    if nearest is None or abs_delta < nearest[0]:
                        nearest = (abs_delta, event)

    if nearest is None:
        return NewsBlackout(False, reason="No high-impact USD news blackout")

    _, event = nearest
    return NewsBlackout(
        blocked=True,
        event=event.name,
        reason=f"News blackout: {event.name} (±{before_minutes}/{after_minutes}m)",
        minutes_to_event=nearest[0],
    )
