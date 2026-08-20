from datetime import datetime, timezone

from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import (
    SessionTier,
    classify_asia_desk,
    classify_full_sessions,
    classify_session,
    in_ema_rsi_ph_window,
    next_session_hint,
    session_allows_asia_scalp,
    session_allows_entry,
)


def test_asia_ph_daytime():
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert session_allows_asia_scalp(ts) is True
    assert session_allows_entry(ts) is False


def test_ema_rsi_until_830pm_manila():
    # 12:30 UTC = 8:30 PM Manila — still EMA_RSI
    ts = datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc)
    window = classify_full_sessions(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_smc_starts_831pm_manila():
    # 12:31 UTC = 8:31 PM Manila — overlap / SMC
    ts = datetime(2026, 7, 20, 12, 31, tzinfo=timezone.utc)
    window = classify_full_sessions(ts)
    assert window.tier == SessionTier.PRIME
    assert window.label == "london_ny_overlap"
    assert session_allows_entry(ts, prime_only=True) is True


def test_afternoon_manila_still_ema_rsi():
    # 08:00 UTC = 4:00 PM Manila — was stand-aside London, now EMA_RSI
    ts = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    window = classify_full_sessions(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_overlap_prime():
    ts = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert session_allows_entry(ts, prime_only=True) is True


def test_asia_desk_only_until_830pm():
    # 8:30 PM Manila
    ts = datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc)
    assert classify_asia_desk(ts).tier == SessionTier.ASIA
    assert in_ema_rsi_ph_window(ts) is True
    # 8:31 PM Manila
    late = datetime(2026, 7, 20, 12, 31, tzinfo=timezone.utc)
    assert classify_asia_desk(late).tier == SessionTier.AVOID
    assert in_ema_rsi_ph_window(late) is False


def test_next_session_after_asia_is_overlap_at_831pm():
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)
    nxt = next_session_hint(ts)
    assert nxt["session"] == "london_ny_overlap"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 12
    assert nxt["minute_utc"] == 31


def test_ema_rsi_starts_7am_manila():
    # Monday 2026-07-20 — 6:59 AM Manila off-hours, 7:00 AM EMA_RSI
    early = datetime(2026, 7, 19, 22, 59, tzinfo=timezone.utc)  # Sun UTC, Mon 6:59 AM PH
    assert classify_full_sessions(early).label == "off_hours"
    start = datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc)  # Sun UTC, Mon 7:00 AM PH
    assert classify_full_sessions(start).label == "asia"
    assert in_ema_rsi_ph_window(start) is True


def test_friday_night_arms_monday_smc():
    """After weekend, first tradeable slot is Mon 00:00 Manila (SMC), not 7AM Asia."""
    ts = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
    nxt = next_session_hint(ts)
    assert nxt["session"] == "london_ny_overlap"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 16
    assert nxt["minute_utc"] == 0


def test_monday_morning_arms_asia_at_7am():
    ts = datetime(2026, 8, 16, 22, 59, tzinfo=timezone.utc)  # Mon 6:59 AM Manila — off
    assert classify_full_sessions(ts).label == "off_hours"
    start = datetime(2026, 8, 16, 23, 0, tzinfo=timezone.utc)  # Mon 7:00 AM Manila
    nxt = next_session_hint(ts)
    assert nxt["session"] == "asia"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 23
    assert classify_full_sessions(start).label == "asia"


def test_weekend_avoided():
    ts = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)
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
