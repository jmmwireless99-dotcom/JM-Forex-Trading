from datetime import datetime, timezone
from pathlib import Path

from app.gold_session_signal import (
    classify_ph_session,
    closed_m1_breakout,
    flow_score,
    format_ph_clock,
    in_hour_range,
    is_small_candle,
    m5_bias,
    ph_from_utc,
    scalper_block_reason,
    scalper_reason_pack,
    scalper_signal_passes,
    signal_card,
    v640_profit_hour_allowed,
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
    assert "arrow=159" in text
    assert "days=1" in text
    assert "InpRequireH1=true" in text
    assert "InpRequireM30=true" in text
    assert "InpRequireH4=false" in text
    assert "InpUseV640ProfitHourRouter=true" in text
    assert "background_color=0" in text
    assert "color=65280" in text
    assert "color=255" in text
    assert "name=BIAS" in text
    assert "name=FAST" in text
    assert "InpShowHourBlockedSetups=true" in text
    assert "InpVisualMode=true" in text


def test_m1_template_exists():
    text = (TPL / "JM_GOLD_Session_M1.tpl").read_text(encoding="utf-8")
    assert "symbol=GOLD#" in text
    assert "period=1" in text
    assert "path=JM_GOLD_Session_Signal_v1" in text
    assert "InpShowSignalCards=false" in text
    assert "InpRequireM30=true" in text


def test_indicator_is_visual_scalper_not_ea():
    mq5 = (ROOT / "mt5" / "Indicators" / "JM_GOLD_Session_Signal_v1.mq5").read_text(encoding="utf-8")
    assert '#property version   "1.33"' in mq5
    assert "OrderSend" not in mq5
    assert "Trade.mqh" not in mq5
    assert "V640ProfitHourAllowed" in mq5
    assert "ClosedM1Breakout" in mq5
    assert "PERIOD_M30" in mq5
    assert "InpRequireM30          = true" in mq5
    assert "InpRequireH1           = true" in mq5
    assert "InpRequireH4           = false" in mq5
    assert "BufBias" in mq5
    assert "BufFast" in mq5
    assert "DrawBiasLabel" in mq5
    assert "MarkSignal" in mq5
    assert "MarkWait" in mq5
    assert "DotY" in mq5
    assert "FeedsReady" in mq5
    assert "TryScalperM5Fallback" in mq5
    assert "sa TAAS ng candle" in mq5
    assert '"ASIAN"' in mq5
    assert '"LONDON"' in mq5
    assert '"NEW YORK"' in mq5
    assert '"OVERLAP"' in mq5
    assert "StyleHourOnCandle" in mq5
    assert "HourRowY" in mq5
    assert "clrYellow" in mq5
    assert "DOT_CODE 159" in mq5
    assert "VisTop()" in mq5
    assert "InpVisualMode          = true" in mq5
    assert "BuildNowLine" in mq5
    assert "DrawNowBadge" in mq5
    assert "NOW: WAIT" in mq5
    assert '" ^ BUY"' in mq5
    assert '" v SELL"' in mq5
    assert "g_seenRates" in mq5
    assert "fullScan" in mq5
    assert "400000" in mq5


def test_ph_hour_label_on_candle():
    from app.gold_session_signal import format_ph_hour_label, session_band

    assert format_ph_hour_label(13) == "1PM"
    assert format_ph_hour_label(1) == "1AM"
    assert format_ph_hour_label(0) == "12AM"
    assert format_ph_hour_label(12) == "12PM"
    assert session_band(13) == "asia"
    assert session_band(21) == "overlap"
    assert session_band(2) == "ny"
    utc = datetime(2026, 9, 16, 13, 17, tzinfo=timezone.utc)
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


def test_v640_hours_match_v677():
    assert v640_profit_hour_allowed(-1, 4) is True
    assert v640_profit_hour_allowed(1, 4) is False
    assert v640_profit_hour_allowed(1, 5) is True
    assert v640_profit_hour_allowed(-1, 5) is True
    assert v640_profit_hour_allowed(-1, 11) is True
    assert v640_profit_hour_allowed(1, 11) is False
    assert v640_profit_hour_allowed(1, 17) is True
    assert v640_profit_hour_allowed(-1, 17) is False
    assert v640_profit_hour_allowed(1, 10) is False


def test_m5_bias_needs_adx_and_ema_gap():
    side, gap = m5_bias(2001.0, 2000.0, adx=18.0, m5atr=2.0)
    assert side == 1
    assert abs(gap - 0.5) < 1e-9
    side, _ = m5_bias(1999.0, 2000.0, adx=18.0, m5atr=2.0)
    assert side == -1
    side, _ = m5_bias(2001.0, 2000.0, adx=10.0, m5atr=2.0)
    assert side == 0


def test_scalper_blocks_mid_adx_and_gap_classes():
    assert scalper_block_reason(1, adx=28.0, gap=0.20) == "MID_ADX"
    assert scalper_block_reason(-1, adx=22.0, gap=0.20) == "SELL_ADX_20_25"
    assert scalper_block_reason(1, adx=18.0, gap=0.70) == "BUY_GAP_050_100"
    assert scalper_block_reason(-1, adx=18.0, gap=0.80) == "SELL_GAP_075_100"
    assert scalper_block_reason(1, adx=18.0, gap=0.10) == "BUY_WEAK_EMA_GAP"
    assert scalper_block_reason(-1, adx=18.0, gap=0.20) is None


def test_small_candle_and_closed_m1_breakout():
    assert is_small_candle(0.30, 0.40) is True
    assert is_small_candle(0.90, 0.40) is False
    assert closed_m1_breakout(1, 10.0, 9.8, brk_high=10.20, brk_low=9.95, atr=2.0) is True
    assert closed_m1_breakout(1, 10.0, 9.8, brk_high=10.01, brk_low=9.95, atr=2.0) is False
    assert closed_m1_breakout(-1, 10.0, 9.8, brk_high=10.05, brk_low=9.60, atr=2.0) is True


def test_flow_score_needs_three():
    score = flow_score(-1, -1, adx=22.0, gap=0.20, rsi=44.0, body_ratio=0.25, range_atr=0.40)
    assert score >= 3


def _ok_kwargs(**overrides):
    base = dict(
        adx=18.0,
        gap=0.20,
        flow=-1,
        rsi=44.0,
        body_ratio=0.25,
        range_atr=0.40,
        small_ok=True,
        breakout_ok=True,
        h1="SELL",
        m30="SELL",
        h4="BUY",
        server_hour=4,
    )
    base.update(overrides)
    return base


def test_h1_buy_blocks_m5_sell_like_false_signal():
    # Previous BB SELL sold the lows while H1 had already flipped BUY.
    ok = scalper_signal_passes(-1, **_ok_kwargs(h1="BUY"))
    assert ok is False
    ok = scalper_signal_passes(-1, **_ok_kwargs(h1="SELL"))
    assert ok is True


def test_m30_required_h4_display_only():
    ok = scalper_signal_passes(-1, **_ok_kwargs(m30="BUY", h4="BUY"))
    assert ok is False
    ok = scalper_signal_passes(-1, **_ok_kwargs(m30="SELL", h4="BUY"))
    assert ok is True
    ok = scalper_signal_passes(-1, **_ok_kwargs(h4="BUY", require_h4=True))
    assert ok is False


def test_v640_blocks_wrong_hour():
    ok = scalper_signal_passes(-1, **_ok_kwargs(server_hour=10))
    assert ok is False
    ok = scalper_signal_passes(-1, **_ok_kwargs(server_hour=4))
    assert ok is True


def test_reason_and_card_saved_for_later_ea():
    reason = scalper_reason_pack(
        session="NEW YORK",
        ph_clock="2:15 AM",
        side="SELL",
        entry=3684.50,
        h4="SELL",
        h1="SELL",
        m30="SELL",
        m5="SELL",
        adx=22.1,
        gap=0.180,
        rsi=44.2,
        score=4,
    )
    assert "SESSION=NEW YORK" in reason
    assert "ENTRY=3684.50" in reason
    assert "M30=SELL" in reason
    assert "SMALL+BREAK" in reason
    card = signal_card(
        side="SELL",
        ph_clock="2:15 AM",
        session="NEW YORK",
        h1="SELL",
        m30="SELL",
        entry=3684.50,
    )
    assert "SELL ▼" in card
    assert "PH TIME: 2:15 AM" in card
    assert "M30 TREND: SELL" in card
    assert "ENTRY: 3684.50" in card
