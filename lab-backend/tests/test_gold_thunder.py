from pathlib import Path
import zipfile

from app.gold_thunder import (
    flow_score,
    is_small_candle,
    m5_bias,
    nfp_blocked,
    pht_hour,
    select_tp_usd,
    thunder_swing_break,
    v640_hour_allowed,
)

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "mt5" / "Experts" / "JM_THUNDER_GOLD_SCALPER.mq5"
ZIP = ROOT / "releases" / "JM-THUNDER-GOLD-SCALPER-Pack.zip"


def test_ea_is_v100_trading_expert():
    mq5 = EA.read_text(encoding="utf-8")
    assert '#define JMT_VERSION "1.0.0"' in mq5
    assert '#property version   "1.00"' in mq5
    assert "#include <Trade/Trade.mqh>" in mq5
    assert "trade.Buy" in mq5
    assert "trade.Sell" in mq5
    assert "InpMagic                  = 26100610" in mq5
    assert "InpFixedSLUsd             = 15.0" in mq5
    assert "InpTP_BaseUsd             = 30.0" in mq5
    assert "GOLD#" in mq5
    assert "ThunderSwing" in mq5
    assert "V640HourAllowed" in mq5
    assert "NfpBlocked" in mq5
    assert "HasOpenPosition" in mq5
    assert mq5.count("#include") == 1


def test_ea_forbids_grid_and_martingale():
    mq5 = EA.read_text(encoding="utf-8")
    low = mq5.lower()
    assert "no grid" in low
    assert "no martingale" in low
    assert "no averaging" in low
    assert "PositionOpen" not in mq5 or mq5.count("trade.Buy") >= 1
    assert "OrderSend" not in mq5
    assert "InpMartingale" not in mq5
    assert "gridLot" not in mq5
    assert "InpGrid" not in mq5


def test_open_trade_always_sets_sl_and_tp():
    mq5 = EA.read_text(encoding="utf-8")
    assert "trade.Buy(lots,g_symbol,0.0,sl,tp,JmtComment())" in mq5
    assert "trade.Sell(lots,g_symbol,0.0,sl,tp,JmtComment())" in mq5


def test_v640_hours_match_v677():
    assert v640_hour_allowed(-1, 4) is True
    assert v640_hour_allowed(1, 4) is False
    assert v640_hour_allowed(1, 5) is True
    assert v640_hour_allowed(-1, 11) is True
    assert v640_hour_allowed(1, 17) is True
    assert v640_hour_allowed(-1, 17) is False
    assert v640_hour_allowed(1, 10) is False
    assert pht_hour(5) == 10


def test_thunder_swing_needs_close_through_prior_swing():
    highs = [2000.0, 2001.0, 1999.0]
    lows = [1990.0, 1988.0, 1989.0]
    assert thunder_swing_break(1, 2002.0, 1995.0, 1998.0, 2001.5, highs, lows) is True
    assert thunder_swing_break(1, 2002.0, 1995.0, 2001.5, 1998.0, highs, lows) is False
    assert thunder_swing_break(-1, 1995.0, 1985.0, 1992.0, 1986.0, highs, lows) is True
    assert thunder_swing_break(-1, 1995.0, 1988.5, 1992.0, 1988.0, highs, lows) is False


def test_m5_bias_and_small_candle_and_score():
    side, gap = m5_bias(2001.0, 2000.0, adx=18.0, m5atr=2.0)
    assert side == 1
    assert abs(gap - 0.5) < 1e-9
    assert m5_bias(2001.0, 2000.0, adx=10.0, m5atr=2.0)[0] == 0
    assert is_small_candle(0.30, 0.40) is True
    assert is_small_candle(0.90, 0.40) is False
    assert flow_score(1, 1, 22.0, 0.10, 55.0, 0.20, 0.40) >= 3


def test_nfp_and_tp_scale():
    assert nfp_blocked(5, 3, 15) is True
    assert nfp_blocked(5, 10, 15) is False
    assert nfp_blocked(4, 3, 15) is False
    assert select_tp_usd(20.0, 0.20, 0.01) == 30.0
    assert select_tp_usd(35.0, 0.70, 0.01) == 45.0
    assert select_tp_usd(35.0, 0.70, 0.02) == 90.0


def test_pack_zip_is_single_file_ea():
    assert ZIP.is_file()
    with zipfile.ZipFile(ZIP) as zf:
        names = set(zf.namelist())
    assert "Experts/JM_THUNDER_GOLD_SCALPER.mq5" in names
    assert "SETUP.txt" in names
    assert not any(n.endswith(".mqh") for n in names)
