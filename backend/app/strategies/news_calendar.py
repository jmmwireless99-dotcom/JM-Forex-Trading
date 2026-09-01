"""USD / London news blackout windows for XAUUSD desk."""

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
    # weekday: 0=Mon … 4=Fri; None = any weekday
    weekday: int | None = None
    week_of_month: int | None = None  # 1..5
    day_of_month: int | None = None
    # First Friday = NFP style
    first_weekday_of_month: int | None = None
    # Last Friday of month (Core PCE style)
    last_weekday_of_month: int | None = None
    # Inclusive day-of-month window (e.g. mid-month CPI)
    day_range: tuple[int, int] | None = None


# High-impact USD events that commonly spike XAUUSD.
# Times are typical US schedule in UTC (EST/EDT shifts ±1h — we use buffers).
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
        # Typical mid-month Tuesday print (approx)
        weekday=1,
        day_range=(10, 16),
    ),
    NewsEvent(
        "FOMC Rate Decision",
        NewsImpact.HIGH,
        utc_hour=18,
        utc_minute=0,
        weekday=2,  # Wednesday
        week_of_month=2,  # ~2nd Wednesday proxy (desk-safe, not every Wed)
    ),
    NewsEvent(
        "Core PCE",
        NewsImpact.HIGH,
        utc_hour=12,
        utc_minute=30,
        last_weekday_of_month=4,  # last Friday of month
    ),
    NewsEvent(
        "US GDP / ISM / Jobless proxy window",
        NewsImpact.MEDIUM,
        utc_hour=14,
        utc_minute=0,
        weekday=3,  # Thursday proxy — avoid daily soft blocks
    ),
]

# High-impact UK / EUR red-folder style windows (London morning risk)
# Anchored to specific weekdays so we do not pause every London open.
LONDON_RED_FOLDER: list[NewsEvent] = [
    NewsEvent("UK CPI / GDP proxy", NewsImpact.HIGH, utc_hour=6, utc_minute=0, weekday=2),
    NewsEvent("UK BOE / Labour proxy", NewsImpact.HIGH, utc_hour=9, utc_minute=30, weekday=3),
    NewsEvent("EUR CPI / GDP proxy", NewsImpact.HIGH, utc_hour=9, utc_minute=0, weekday=2),
    NewsEvent(
        "ECB rate decision proxy",
        NewsImpact.HIGH,
        utc_hour=12,
        utc_minute=15,
        weekday=3,
        week_of_month=2,
    ),
]


@dataclass(frozen=True)
class NewsBlackout:
    blocked: bool
    event: str | None = None
    reason: str = ""
    minutes_to_event: int | None = None


@dataclass(frozen=True)
class NewsDayEvent:
    """One scheduled high-impact print on a calendar day."""

    event: NewsEvent
    when: datetime


@dataclass(frozen=True)
class NewsTradingWindow:
    """Active post-release momentum window for NewsBreakout."""

    active: bool
    event: str | None = None
    reason: str = ""
    minutes_from_release: int | None = None
    release_at: datetime | None = None


def news_events_on_day(ts: datetime, *, include_medium: bool = False) -> list[NewsDayEvent]:
    """High-impact USD events scheduled on this UTC calendar day."""
    ts = ts.astimezone(timezone.utc)
    day = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    out: list[NewsDayEvent] = []
    for event in USD_GOLD_EVENTS:
        if event.impact == NewsImpact.MEDIUM and not include_medium:
            continue
        for when in _event_occurrences(event, day):
            out.append(NewsDayEvent(event=event, when=when))
    return sorted(out, key=lambda row: row.when)


def is_news_day(ts: datetime, *, include_medium: bool = False) -> bool:
    """True when at least one high-impact USD gold event is scheduled today."""
    return bool(news_events_on_day(ts, include_medium=include_medium))


def primary_news_event(ts: datetime) -> NewsDayEvent | None:
    rows = news_events_on_day(ts)
    return rows[0] if rows else None


def _nearest_scheduled_news(
    ts: datetime,
    *,
    include_medium: bool = False,
) -> tuple[NewsDayEvent, int] | None:
    """Return (event, minutes_until_release) for the closest scheduled print.

    Positive minutes_until_release = release is still in the future.
    Negative = release already happened.
    """
    ts = ts.astimezone(timezone.utc)
    best: tuple[int, NewsDayEvent, int] | None = None
    for day in (ts - timedelta(days=1), ts, ts + timedelta(days=1)):
        for row in news_events_on_day(day, include_medium=include_medium):
            delta_min = int((row.when - ts).total_seconds() // 60)
            abs_delta = abs(delta_min)
            if best is None or abs_delta < best[0]:
                best = (abs_delta, row, delta_min)
    if best is None:
        return None
    _, row, delta_min = best
    return row, delta_min


def should_run_news_strategy(
    ts: datetime,
    *,
    pre_release_minutes: int = 60,
    post_release_minutes: int = 60,
) -> NewsTradingWindow:
    """True when PH gabi/evening and within 1hr before → 1hr after scheduled news."""
    from app.strategies.session import is_ph_evening_news_window

    ts = ts.astimezone(timezone.utc)
    if ts.weekday() >= 5:
        return NewsTradingWindow(active=False, reason="Weekend — NewsBreakout off")

    if not is_ph_evening_news_window(ts):
        return NewsTradingWindow(
            active=False,
            reason="NewsBreakout: PH daytime — EMA_RSI/SMC until evening",
        )

    nearest = _nearest_scheduled_news(ts)
    if nearest is None:
        return NewsTradingWindow(active=False, reason="No scheduled high-impact news")

    row, minutes_until = nearest
    minutes_from_release = -minutes_until

    if minutes_until > pre_release_minutes:
        return NewsTradingWindow(
            active=False,
            event=row.event.name,
            reason=(
                f"NewsBreakout arms T-{pre_release_minutes}m "
                f"({row.event.name} in {minutes_until}m)"
            ),
            minutes_from_release=minutes_from_release,
            release_at=row.when,
        )

    if minutes_until < -post_release_minutes:
        return NewsTradingWindow(
            active=False,
            event=row.event.name,
            reason=f"News window ended (+{post_release_minutes}m after {row.event.name})",
            minutes_from_release=minutes_from_release,
            release_at=row.when,
        )

    if minutes_until >= 0:
        phase = f"T-{minutes_until}m pre-release"
    else:
        phase = f"+{-minutes_until}m post-release"

    return NewsTradingWindow(
        active=True,
        event=row.event.name,
        reason=f"NewsBreakout active: {row.event.name} ({phase})",
        minutes_from_release=minutes_from_release,
        release_at=row.when,
    )


def check_news_trading_window(
    ts: datetime,
    *,
    post_release_start_min: int = 5,
    post_release_end_min: int = 60,
) -> NewsTradingWindow:
    """Entry window for NewsBreakout — post-spike only, inside the armed period."""
    armed = should_run_news_strategy(
        ts,
        pre_release_minutes=60,
        post_release_minutes=post_release_end_min,
    )
    if not armed.active:
        return armed

    ts = ts.astimezone(timezone.utc)
    if armed.release_at is None:
        return NewsTradingWindow(active=False, reason="No release time")

    delta_min = int((ts - armed.release_at).total_seconds() // 60)
    if delta_min < post_release_start_min:
        minutes_until = int((armed.release_at - ts).total_seconds() // 60)
        wait = (
            f"{minutes_until}m until release"
            if minutes_until > 0
            else f"release { -minutes_until}m ago — wait +{post_release_start_min}m"
        )
        return NewsTradingWindow(
            active=False,
            event=armed.event,
            reason=f"Pre-release armed — {wait} ({armed.event})",
            minutes_from_release=delta_min,
            release_at=armed.release_at,
        )

    if delta_min > post_release_end_min:
        return NewsTradingWindow(
            active=False,
            event=armed.event,
            reason=f"Post-release window closed (+{post_release_end_min}m)",
            minutes_from_release=delta_min,
            release_at=armed.release_at,
        )

    return NewsTradingWindow(
        active=True,
        event=armed.event,
        reason=f"News entry window: {armed.event} (+{delta_min}m post-release)",
        minutes_from_release=delta_min,
        release_at=armed.release_at,
    )


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


def _last_weekday(year: int, month: int, weekday: int) -> int | None:
    last = None
    for day in range(1, 32):
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            break
        if dt.weekday() == weekday:
            last = day
    return last


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

    if event.last_weekday_of_month is not None:
        target = _last_weekday(y, m, event.last_weekday_of_month)
        if target == d:
            candidates.append(
                datetime(y, m, d, event.utc_hour, event.utc_minute, tzinfo=timezone.utc)
            )
        return candidates

    if event.weekday is not None and day.weekday() != event.weekday:
        return []

    if event.week_of_month is not None:
        target = _nth_weekday(y, m, event.weekday if event.weekday is not None else day.weekday(), event.week_of_month)
        if target != d:
            return []

    if event.day_of_month is not None and event.day_of_month != d:
        return []

    if event.day_range is not None:
        lo, hi = event.day_range
        if not (lo <= d <= hi):
            return []

    if day.weekday() >= 5:
        return []

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


def check_london_news_blackout(
    ts: datetime,
    *,
    before_minutes: int = 15,
    after_minutes: int = 10,
) -> NewsBlackout:
    """Pause London Judas entries 15m before UK/EUR red-folder style events."""
    ts = ts.astimezone(timezone.utc)
    if ts.weekday() >= 5:
        return NewsBlackout(False, reason="Weekend")

    nearest: tuple[int, NewsEvent] | None = None
    for day in (ts - timedelta(days=1), ts, ts + timedelta(days=1)):
        for event in LONDON_RED_FOLDER:
            for when in _event_occurrences(event, day):
                delta_min = int((when - ts).total_seconds() // 60)
                if -before_minutes <= delta_min <= after_minutes:
                    abs_delta = abs(delta_min)
                    if nearest is None or abs_delta < nearest[0]:
                        nearest = (abs_delta, event)

    # Also respect USD high-impact during London window
    usd = check_news_blackout(ts, before_minutes=before_minutes, after_minutes=after_minutes)
    if usd.blocked:
        return usd

    if nearest is None:
        return NewsBlackout(False, reason="No UK/EUR red-folder blackout")

    _, event = nearest
    return NewsBlackout(
        blocked=True,
        event=event.name,
        reason=f"London news pause: {event.name} (−{before_minutes}m)",
        minutes_to_event=nearest[0],
    )
