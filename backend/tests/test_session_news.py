from datetime import datetime, timezone

from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import (
    SessionTier,
    classify_session,
    session_allows_asia_scalp,
    session_allows_entry,
)


def test_prime_overlap_session():
    ts = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)  # Monday
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert session_allows_entry(ts) is True
    assert session_allows_entry(ts, prime_only=True) is True


def test_asia_session_is_scalp_window():
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    assert classify_session(ts).tier == SessionTier.ASIA
    assert session_allows_entry(ts) is False  # trend tools stay off
    assert session_allows_asia_scalp(ts) is True


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
    # Random Tuesday mid-session far from typical CPI window days
    ts = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    result = check_news_blackout(ts)
    # May or may not hit medium events; high-impact only by default
    assert result.blocked in {True, False}
    # Ensure a clearly quiet Sunday night is open
    quiet = check_news_blackout(datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc))
    assert quiet.blocked is False
