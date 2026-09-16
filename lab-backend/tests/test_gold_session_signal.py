from datetime import datetime, timezone
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[2]
TPL = ROOT / "mt5" / "Templates"


def test_m5_template_is_gold_session_view():
    text = (TPL / "JM_GOLD_Session_M5.tpl").read_text(encoding="utf-8")
    assert "symbol=GOLD#" in text
    assert "period=5" in text
    assert "path=JM_GOLD_Session_Signal_v1" in text
    assert "InpDrawPhHours=true" in text
    assert "InpDrawDaily=true" in text
    assert "InpDrawSessions=true" in text
    assert "arrow=233" in text  # BUY
    assert "arrow=234" in text  # SELL
    assert "days=1" in text  # MT5 daily period separators
    assert "InpEasyArrows=true" in text
    assert "InpRequireRsi=false" in text
    assert "InpRequireBb=false" in text
    assert "InpRequireH1=false" in text
    assert "background_color=0" in text
    assert "color=16776960" in text  # aqua BUY
    assert "color=16711935" in text  # magenta SELL
    assert "InpDrawHourLines=false" in text


def test_m1_template_exists():
    text = (TPL / "JM_GOLD_Session_M1.tpl").read_text(encoding="utf-8")
    assert "symbol=GOLD#" in text
    assert "period=1" in text
    assert "path=JM_GOLD_Session_Signal_v1" in text
    assert "InpShowSignalCards=false" in text
    assert "InpEasyArrows=true" in text


def test_indicator_draws_names_hours_and_easy_arrows():
    mq5 = (ROOT / "mt5" / "Indicators" / "JM_GOLD_Session_Signal_v1.mq5").read_text(encoding="utf-8")
    assert '#property version   "1.21"' in mq5
    assert 'InpEasyArrows          = true' in mq5
    assert '"ASIAN"' in mq5
    assert '"LONDON"' in mq5
    assert '"NEW YORK"' in mq5
    assert '"OVERLAP"' in mq5
    assert "StyleHourOnCandle" in mq5
    assert "HourRowY" in mq5
    assert "OBJPROP_ANGLE,90" in mq5
    assert "clrYellow" in mq5
    assert "clrAqua" in mq5
    assert "clrMagenta" in mq5
    assert "DrawObjArrow" in mq5
    assert "VisTop()" in mq5


def test_easy_arrows_ignore_rsi_bb_h1():
    ok = signal_passes(
        "BUY",
        ema_side="BUY",
        rsi_ok=False,
        bb_ok=False,
        candle=True,
        h4="SELL",
        h1="SELL",
        m15="SELL",
        easy_arrows=True,
    )
    assert ok is True


def test_ph_hour_label_on_candle():
    from app.gold_session_signal import format_ph_hour_label, session_band

    assert format_ph_hour_label(13) == "1PM"
    assert format_ph_hour_label(1) == "1AM"
    assert format_ph_hour_label(0) == "12AM"
    assert format_ph_hour_label(12) == "12PM"
    assert session_band(13) == "asia"       # 1PM PH
    assert session_band(21) == "overlap"    # 9PM PH
    assert session_band(2) == "ny"
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
