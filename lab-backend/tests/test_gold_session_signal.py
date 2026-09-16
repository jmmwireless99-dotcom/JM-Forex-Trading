from datetime import datetime, timezone

from app.gold_session_signal import (
    bb_bounce,
    classify_ph_session,
    format_ph_clock,
    in_hour_range,
    ph_from_utc,
    reason_pack,
    signal_card,
    signal_passes,
)


def test_ph_clock_from_utc():
    utc = datetime(2026, 9, 16, 13, 17, tzinfo=timezone.utc)  # 9:17 PM PH
    ph = ph_from_utc(utc)
    assert ph.hour == 21 and ph.minute == 17
    assert format_ph_clock(ph) == "9:17 PM"


def test_wrap_hour_range_ny():
    assert in_hour_range(21, 20, 5) is True
    assert in_hour_range(2, 20, 5) is True
    assert in_hour_range(6, 20, 5) is False
    assert in_hour_range(19, 20, 5) is False


def test_session_priority_overlap():
    assert classify_ph_session(21) == "LONDON-NY OVERLAP"
    assert classify_ph_session(2) == "NEW YORK"
    assert classify_ph_session(17) == "LONDON"
    assert classify_ph_session(10) == "ASIAN/TOKYO"
    assert classify_ph_session(6) == "OFF-HOURS"


def test_h1_filter_blocks_countertrend_when_required():
    ok = signal_passes(
        "BUY",
        ema_side="BUY",
        rsi_ok=True,
        bb_ok=True,
        candle=True,
        h4="SELL",
        h1="SELL",
        m15="BUY",
        require_h4=False,
        require_h1=True,
        require_m15=False,
    )
    assert ok is False


def test_h4_and_m15_optional_so_entries_are_not_starved():
    ok = signal_passes(
        "BUY",
        ema_side="BUY",
        rsi_ok=True,
        bb_ok=True,
        candle=True,
        h4="SELL",
        h1="BUY",
        m15="SELL",
        require_h4=False,
        require_h1=True,
        require_m15=False,
    )
    assert ok is True


def test_bb_buy_bounce():
    assert bb_bounce("BUY", 10.4, 9.9, 10.2, 10.05, bb_upper=10.5, bb_lower=10.0) is True
    assert bb_bounce("BUY", 10.4, 10.1, 10.2, 10.05, bb_upper=10.5, bb_lower=10.0) is False


def test_reason_and_card_saved_for_later_ea():
    reason = reason_pack(
        session="NEW YORK",
        ph_clock="9:17 PM",
        side="BUY",
        entry=3684.50,
        h4="BUY",
        h1="BUY",
        m15="BUY",
        ema_side="BUY",
        rsi=58.2,
        bb_tag="LOWER_BOUNCE",
        candle="BULL",
    )
    assert "SESSION=NEW YORK" in reason
    assert "ENTRY=3684.50" in reason
    card = signal_card(
        side="BUY",
        ph_clock="9:17 PM",
        session="NEW YORK",
        h1="BUY",
        m15="BUY",
        entry=3684.50,
    )
    assert "BUY ▲" in card
    assert "PH TIME: 9:17 PM" in card
    assert "ENTRY: 3684.50" in card
