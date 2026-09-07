from datetime import datetime, timezone

from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import (
    SessionTier,
    classify_asia_desk,
    classify_session,
    next_session_hint,
    session_allows_asia_scalp,
    session_allows_entry,
)


def test_asia_ph_morning():
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)  # 10AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_afternoon_ph_still_asia():
    ts = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)  # 4PM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_evening_ph_still_asia():
    ts = datetime(2026, 7, 20, 11, 30, tzinfo=timezone.utc)  # 7:30PM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_8pm_ph_starts_smc():
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # 8PM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert window.label == "london_ny_overlap"


def test_2am_ph_starts_early_ema():
    ts = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)  # 2AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "off_hours"


def test_630am_ph_outside_desk():
    ts = datetime(2026, 7, 20, 22, 30, tzinfo=timezone.utc)  # 6:30AM PH gap
    window = classify_session(ts)
    assert window.tier == SessionTier.AVOID
    assert window.label == "outside_asia_desk"


def test_next_session_after_asia_is_smc():
    ts = datetime(2026, 7, 20, 11, 0, tzinfo=timezone.utc)  # 7PM PH Asia
    nxt = next_session_hint(ts)
    assert nxt["session"] == "london_ny_overlap"
    assert nxt["strategy"] == "AI_ML"


def test_weekend_avoided():
    ts = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)
    assert classify_session(ts).tier == SessionTier.AVOID


def test_nfp_blackout_first_friday():
    ts = datetime(2026, 7, 3, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is True
    assert "NFP" in result.event
