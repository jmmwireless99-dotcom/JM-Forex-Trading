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


def test_asia_ph_daytime():
    # 02:00 UTC = 10:00AM PH — Asia EMA window
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert session_allows_asia_scalp(ts) is True
    assert session_allows_entry(ts) is False


def test_afternoon_ph_still_asia():
    # 08:00 UTC = 4:00PM PH — still Asia until 8:00PM
    ts = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_evening_ph_still_asia():
    # 11:30 UTC = 7:30PM PH — Asia through 8:00PM
    ts = datetime(2026, 7, 20, 11, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "asia"


def test_8pm_ph_starts_smc():
    # 12:00 UTC = 8:00PM PH — SMC window
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert window.label == "london_ny_overlap"
    assert session_allows_entry(ts, prime_only=True) is True


def test_midnight_ph_still_smc():
    ts = datetime(2026, 7, 20, 16, 0, tzinfo=timezone.utc)  # 12:00AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert window.label == "london_ny_overlap"


def test_130am_ph_still_smc():
    ts = datetime(2026, 7, 20, 17, 30, tzinfo=timezone.utc)  # 1:30AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert window.label == "london_ny_overlap"


def test_2am_ph_starts_early_ema():
    ts = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)  # 2:00AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "off_hours"


def test_5am_ph_early_ema():
    ts = datetime(2026, 7, 20, 21, 0, tzinfo=timezone.utc)  # 5:00AM PH
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert window.label == "off_hours"


def test_asia_desk_smc_through_2am():
    ts = datetime(2026, 7, 20, 17, 0, tzinfo=timezone.utc)  # 1:00AM PH
    assert classify_asia_desk(ts).label == "london_ny_overlap"


def test_next_session_after_asia_is_smc():
    ts = datetime(2026, 7, 20, 11, 0, tzinfo=timezone.utc)  # 7PM PH Asia
    nxt = next_session_hint(ts)
    assert nxt["session"] == "london_ny_overlap"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 12


def test_next_session_after_smc_is_early_ema():
    ts = datetime(2026, 7, 20, 17, 30, tzinfo=timezone.utc)  # 1:30AM PH SMC
    nxt = next_session_hint(ts)
    assert nxt["session"] == "off_hours"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 18


def test_next_session_after_early_ema_is_asia():
    ts = datetime(2026, 7, 20, 21, 0, tzinfo=timezone.utc)  # 5AM PH early EMA
    nxt = next_session_hint(ts)
    assert nxt["session"] == "asia"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 23


def test_friday_pre_dawn_next_is_asia():
    # Fri 22:00 UTC = 6:00AM PH early EMA; next Asia at UTC 23
    ts = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
    nxt = next_session_hint(ts)
    assert nxt["session"] == "asia"
    assert nxt["strategy"] == "AI_ML"
    assert nxt["hour_utc"] == 23


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


def test_is_news_day_core_pce_friday():
    from app.strategies.news_calendar import is_news_day, primary_news_event

    ts = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)
    assert is_news_day(ts) is True
    assert primary_news_event(ts) is not None
    assert primary_news_event(ts).name == "Core PCE"
