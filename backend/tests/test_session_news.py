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
    # 02:00 UTC = 10:00AM PH — inside Aug 19 Asia window
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"
    assert session_allows_asia_scalp(ts) is True
    assert session_allows_entry(ts) is False


def test_asia_ph_8am_start():
    # 00:00 UTC = 8:00AM PH — first bar of Asia window
    ts = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_asia_ph_before_8am_stand_aside():
    # 23:30 UTC = 7:30AM PH — before Aug 19 Asia open
    ts = datetime(2026, 7, 19, 23, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.AVOID
    assert window.label == "outside_asia_desk"


def test_asia_ph_3pm_end():
    # 06:30 UTC = 2:30PM PH — still inside Asia window
    ts = datetime(2026, 7, 20, 6, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_after_3pm_ph_stand_aside():
    # 07:00 UTC = 3:00PM PH — Asia window closed
    ts = datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.AVOID
    assert window.label == "outside_asia_desk"


def test_evening_ph_stand_aside():
    # 12:00 UTC = 8:00PM PH — flat outside Asia desk
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.AVOID
    assert window.label == "outside_asia_desk"


def test_next_session_after_asia_is_next_day_asia():
    ts = datetime(2026, 7, 20, 6, 0, tzinfo=timezone.utc)  # 2PM PH Asia
    nxt = next_session_hint(ts)
    assert nxt["session"] == "asia"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 0


def test_next_session_from_outside_waits_for_asia():
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # 8PM PH outside desk
    nxt = next_session_hint(ts)
    assert nxt["session"] == "asia"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 0


def test_asia_desk_matches_classify_session():
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # 11AM PH
    assert classify_asia_desk(ts).label == "asia"
    assert classify_session(ts).label == "asia"


def test_weekend_avoided():
    ts = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)  # Sunday
    assert classify_session(ts).tier == SessionTier.AVOID


def test_nfp_blackout_first_friday():
    ts = datetime(2026, 7, 3, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is True
    assert result.event is not None
    assert "NFP" in result.event


def test_quiet_day_not_blocked():
    quiet = check_news_blackout(datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc))
    assert quiet.blocked is False


def test_core_pce_not_every_late_month_day():
    ts = datetime(2026, 7, 21, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is False


def test_core_pce_last_friday_blackout():
    ts = datetime(2026, 7, 31, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is True
    assert result.event == "Core PCE"
