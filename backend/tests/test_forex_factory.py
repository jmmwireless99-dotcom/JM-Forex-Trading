"""Forex Factory live calendar feed."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.forex_factory import (
    ForexFactoryCalendar,
    _parse_row,
    reset_forex_factory_calendar,
)


SAMPLE = [
    {
        "title": "ISM Manufacturing PMI",
        "country": "USD",
        "date": "2026-09-01T10:00:00-04:00",
        "impact": "High",
        "forecast": "49.0",
        "previous": "48.7",
        "actual": "",
    },
    {
        "title": "JOLTS Job Openings",
        "country": "USD",
        "date": "2026-09-01T10:00:00-04:00",
        "impact": "Medium",
        "forecast": "7.40M",
        "previous": "7.44M",
        "actual": "",
    },
]


def test_parse_ff_row():
    ev = _parse_row(SAMPLE[0])
    assert ev is not None
    assert ev.title == "ISM Manufacturing PMI"
    assert ev.country == "USD"
    assert ev.impact == "High"
    assert ev.when.hour == 14  # 10:00 EDT -> 14:00 UTC


def test_nearest_usd_high_event():
    cal = ForexFactoryCalendar(refresh_seconds=60)
    with patch.object(cal, "events", return_value=[_parse_row(SAMPLE[0])]):  # type: ignore[list-item]
        ts = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)  # T-60m
        nearest = cal.nearest_event(ts, countries=("USD",), min_impact="High")
    assert nearest is not None
    ev, delta = nearest
    assert ev.title == "ISM Manufacturing PMI"
    assert delta == 60


def test_desk_payload_includes_today_events():
    cal = ForexFactoryCalendar(refresh_seconds=60)
    parsed = [_parse_row(row) for row in SAMPLE]
    with patch.object(cal, "events", return_value=[p for p in parsed if p]):  # type: ignore[arg-type]
        payload = cal.desk_payload(datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc))
    assert payload["source"] == "forexfactory"
    assert len(payload["events_today"]) >= 1
    assert payload["next_usd_high"]["title"] == "ISM Manufacturing PMI"


@pytest.fixture(autouse=True)
def _reset_calendar():
    reset_forex_factory_calendar()
    yield
    reset_forex_factory_calendar()
