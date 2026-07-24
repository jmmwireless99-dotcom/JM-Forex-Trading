from datetime import datetime, timezone

from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import (
    SessionTier,
    classify_asia_desk,
    classify_full_sessions,
    classify_session,
    next_session_hint,
    session_allows_asia_scalp,
    session_allows_entry,
)


def test_asia_ph_daytime():
    # 02:00 UTC = Asia box / EMA window
    ts = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ASIA
    assert session_allows_asia_scalp(ts) is True
    assert session_allows_entry(ts) is False


def test_london_judas_window():
    # 08:00 UTC — primary Judas sweep/entry (must NOT be Asia)
    ts = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ALLOWED
    assert window.label == "london"
    assert session_allows_entry(ts) is True


def test_london_wind_down_keeps_ema_auto():
    # 11:30 UTC — Judas cools; EMA stays armed for always-on auto
    ts = datetime(2026, 7, 20, 11, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ALLOWED
    assert window.label == "london_wind_down"
    assert session_allows_entry(ts) is True


def test_london_close_keeps_ema_auto():
    # 12:00 UTC — Judas limits still killed; EMA auto remains allowed
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.ALLOWED
    assert window.label == "london_close"
    assert session_allows_entry(ts) is True


def test_overlap_prime():
    ts = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)
    window = classify_session(ts)
    assert window.tier == SessionTier.PRIME
    assert session_allows_entry(ts, prime_only=True) is True


def test_asia_desk_only_blocks_after_5pm():
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    assert classify_asia_desk(ts).tier == SessionTier.AVOID
    assert classify_full_sessions(ts).label == "london_close"


def test_next_session_after_asia_is_london():
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # Asia
    nxt = next_session_hint(ts)
    assert nxt["session"] == "london"
    assert nxt["strategy"] == "London_Judas_Sweep"


def test_schedule_table_has_ph_and_hourly_row():
    from app.strategies.session import schedule_table

    rows = schedule_table()
    assert any(r["session"] == "asia" and r["strategies"] == "EMA_RSI_Scalp" for r in rows)
    assert any(r["session"] == "london" and "07:00" in r["utc"] for r in rows)
    assert any(r["session"] == "london_ny_overlap" and r["strategies"] == "Liquidity_Sweep_SMC" for r in rows)
    asia = next(r for r in rows if r["session"] == "asia")
    assert asia["ph"] == "08:00-14:59"
    hourly = next(r for r in rows if r["session"] == "hourly")
    assert hourly["slot"] == "Auto transfer"
    assert "hour" in hourly["utc"].lower()
    assert any(r["session"] == "london_close" and r["strategies"] == "EMA_RSI_Scalp" for r in rows)
    assert any(r["session"] == "off_hours" and r["strategies"] == "EMA_RSI_Scalp" for r in rows)


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
    # Tue Jul 21 2026 is NOT last Friday — must not blackout for Core PCE
    ts = datetime(2026, 7, 21, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is False


def test_core_pce_last_friday_blackout():
    # Last Friday of July 2026 = Jul 31
    ts = datetime(2026, 7, 31, 12, 20, tzinfo=timezone.utc)
    result = check_news_blackout(ts, before_minutes=45, after_minutes=30)
    assert result.blocked is True
    assert result.event == "Core PCE"
