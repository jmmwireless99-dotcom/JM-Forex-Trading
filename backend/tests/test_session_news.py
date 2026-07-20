from datetime import datetime, timezone

from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import (
    SessionTier,
    classify_asia_desk,
    classify_full_sessions,
    classify_session,
    session_allows_asia_scalp,
    session_allows_entry,
)


def test_asia_desk_open_ph_daytime():
    # 02:00 UTC = 10:00 PH → inside Asia desk
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert session_allows_asia_scalp(ts) is True
    assert session_allows_entry(ts) is False  # trend tools stay off


def test_asia_desk_closed_after_ph_7pm():
    # 12:00 UTC = 20:00 PH → outside Asia desk
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.AVOID
    assert window.label == "outside_asia_desk"
    assert session_allows_asia_scalp(ts) is False


def test_london_utc_still_asia_desk_until_ph_7pm():
    # 10:00 UTC = 18:00 PH → still Asia desk (until 19:00 PH / 11:00 UTC)
    ts = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    assert classify_asia_desk(ts).tier == SessionTier.ASIA
    assert classify_session(ts).tier == SessionTier.ASIA


def test_full_sessions_prime_overlap():
    ts = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)  # Monday
    window = classify_full_sessions(ts)
    assert window.tier == SessionTier.PRIME
    assert session_allows_entry(ts) is False  # asia_desk_only default blocks entry helpers


def test_weekend_avoided():
    ts = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)  # Sunday
    assert classify_session(ts).tier == SessionTier.AVOID


def test_nfp_blackout_first_friday():
    # 3 July 2026 is the first Friday of July
    ts = datetime(2026, 7, 3, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is True
    assert result.event is not None
    assert "NFP" in result.event


def test_quiet_day_not_blocked():
    # Ensure a clearly quiet Sunday night is open
    quiet = check_news_blackout(datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc))
    assert quiet.blocked is False
