"""Live economic calendar feed (Forex Factory JSON mirror)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

FF_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_NEXT_WEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

IMPACT_RANK = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0, "Non-Economic": 0}


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    country: str
    when: datetime
    impact: str
    forecast: str = ""
    previous: str = ""
    actual: str = ""

    @property
    def impact_rank(self) -> int:
        return IMPACT_RANK.get(self.impact, 0)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "country": self.country,
            "impact": self.impact,
            "when_utc": self.when.astimezone(timezone.utc).isoformat(),
            "forecast": self.forecast,
            "previous": self.previous,
            "actual": self.actual,
        }


def _parse_ff_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_row(row: dict) -> CalendarEvent | None:
    when = _parse_ff_datetime(row.get("date"))
    if when is None:
        return None
    title = str(row.get("title") or "").strip()
    if not title:
        return None
    return CalendarEvent(
        title=title,
        country=str(row.get("country") or "").strip().upper(),
        when=when,
        impact=str(row.get("impact") or "Low").strip(),
        forecast=str(row.get("forecast") or ""),
        previous=str(row.get("previous") or ""),
        actual=str(row.get("actual") or ""),
    )


class ForexFactoryCalendar:
    """Cached Forex Factory calendar (refreshed every few minutes)."""

    def __init__(self, *, refresh_seconds: int = 300) -> None:
        self.refresh_seconds = max(60, refresh_seconds)
        self._lock = threading.RLock()
        self._events: list[CalendarEvent] = []
        self._fetched_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def fetched_at(self) -> datetime | None:
        return self._fetched_at

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def source(self) -> str:
        return "forexfactory"

    def _needs_refresh(self) -> bool:
        if not self._events or self._fetched_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._fetched_at).total_seconds()
        return age >= self.refresh_seconds

    def refresh(self, *, force: bool = False) -> bool:
        with self._lock:
            if not force and not self._needs_refresh():
                return bool(self._events)
        rows: list[CalendarEvent] = []
        err: str | None = None
        for url in (FF_THIS_WEEK, FF_NEXT_WEEK):
            try:
                resp = httpx.get(
                    url,
                    timeout=12.0,
                    headers={"User-Agent": "JM-FX-Desk/1.0"},
                )
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, list):
                    continue
                for raw in payload:
                    if not isinstance(raw, dict):
                        continue
                    ev = _parse_row(raw)
                    if ev is not None:
                        rows.append(ev)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                log.warning("forex factory fetch failed url=%s err=%s", url, exc)
        with self._lock:
            if rows:
                dedup: dict[tuple[str, str, int], CalendarEvent] = {}
                for ev in rows:
                    key = (ev.title, ev.country, int(ev.when.timestamp()))
                    dedup[key] = ev
                self._events = sorted(dedup.values(), key=lambda e: e.when)
                self._fetched_at = datetime.now(timezone.utc)
                self._last_error = None
                return True
            self._last_error = err or "empty calendar feed"
            return bool(self._events)

    def events(self, *, force_refresh: bool = False) -> list[CalendarEvent]:
        if force_refresh or self._needs_refresh():
            self.refresh(force=force_refresh)
        with self._lock:
            return list(self._events)

    def events_between(
        self,
        start: datetime,
        end: datetime,
        *,
        countries: tuple[str, ...] = ("USD", "EUR", "GBP"),
        min_impact: str = "Low",
    ) -> list[CalendarEvent]:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        min_rank = IMPACT_RANK.get(min_impact, 1)
        out = [
            ev
            for ev in self.events()
            if start <= ev.when <= end
            and ev.country in countries
            and ev.impact_rank >= min_rank
        ]
        return sorted(out, key=lambda e: e.when)

    def events_on_day(
        self,
        ts: datetime,
        *,
        countries: tuple[str, ...] = ("USD",),
        min_impact: str = "High",
    ) -> list[CalendarEvent]:
        ts = ts.astimezone(timezone.utc)
        day_start = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
        return self.events_between(
            day_start, day_end, countries=countries, min_impact=min_impact
        )

    def nearest_event(
        self,
        ts: datetime,
        *,
        countries: tuple[str, ...] = ("USD",),
        min_impact: str = "High",
        horizon_hours: int = 36,
    ) -> tuple[CalendarEvent, int] | None:
        """Closest event to now; returns (event, minutes_until_release)."""
        ts = ts.astimezone(timezone.utc)
        lo = ts - timedelta(hours=horizon_hours)
        hi = ts + timedelta(hours=horizon_hours)
        candidates = self.events_between(lo, hi, countries=countries, min_impact=min_impact)
        if not candidates:
            return None
        best: tuple[int, CalendarEvent, int] | None = None
        for ev in candidates:
            delta = int((ev.when - ts).total_seconds() // 60)
            abs_delta = abs(delta)
            if best is None or abs_delta < best[0]:
                best = (abs_delta, ev, delta)
        if best is None:
            return None
        _, ev, delta = best
        return ev, delta

    def desk_payload(self, ts: datetime | None = None) -> dict:
        now = (ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.refresh()
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        upcoming_end = now + timedelta(hours=30)
        today = self.events_between(
            day_start, day_end, countries=("USD", "EUR", "GBP"), min_impact="Low"
        )
        upcoming = self.events_between(
            now, upcoming_end, countries=("USD", "EUR", "GBP"), min_impact="Low"
        )
        nearest_high = self.nearest_event(now, countries=("USD",), min_impact="High")
        rows = []
        for ev in today:
            minutes_until = int((ev.when - now).total_seconds() // 60)
            row = {
                **ev.as_dict(),
                "minutes_until": minutes_until,
                "imminent": -60 <= minutes_until <= 60,
                "is_past": minutes_until < -60,
            }
            rows.append(row)
        return {
            "source": self.source,
            "source_url": "https://www.forexfactory.com/calendar",
            "fetched_at": self._fetched_at.isoformat() if self._fetched_at else None,
            "last_error": self._last_error,
            "events_today": rows,
            "events_upcoming": [ev.as_dict() for ev in upcoming[:24]],
            "next_usd_high": (
                {
                    **nearest_high[0].as_dict(),
                    "minutes_until": nearest_high[1],
                }
                if nearest_high
                else None
            ),
        }


_calendar: ForexFactoryCalendar | None = None
_calendar_lock = threading.Lock()


def get_forex_factory_calendar(*, refresh_seconds: int = 300) -> ForexFactoryCalendar:
    global _calendar
    with _calendar_lock:
        if _calendar is None:
            _calendar = ForexFactoryCalendar(refresh_seconds=refresh_seconds)
        return _calendar


def reset_forex_factory_calendar() -> None:
    global _calendar
    with _calendar_lock:
        _calendar = None
