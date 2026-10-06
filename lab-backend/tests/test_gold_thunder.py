from pathlib import Path
import zipfile

from app.gold_thunder import (
    DEF_TRAIL_DISTANCE_PTS,
    DEF_TRAIL_DISTANCE_USD,
    DEF_TRAIL_START_PTS,
    DEF_TRAIL_START_USD,
    DEF_TRAIL_STEP_PTS,
    DEF_TRAIL_STEP_USD,
    EA_MAGIC,
    apply_trail,
    default_trail_points,
    has_manual_exposure,
    in_session,
    is_manual_pending,
    is_manual_position,
    pause_auto_when_manual,
    stop_entry,
    swing_unbroken,
    usd_to_points,
)

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "mt5" / "Experts" / "JM_THUNDER_GOLD_SCALPER.mq5"
SETUP = ROOT / "mt5" / "JM_THUNDER_GOLD_SCALPER_SETUP.txt"
ZIP = ROOT / "releases" / "JM-THUNDER-GOLD-SCALPER-Pack.zip"


def test_ea_is_v203_structure_plus_manual_trail():
    mq5 = EA.read_text(encoding="utf-8")
    assert '#property version   "2.03"' in mq5
    assert "JM Thunder Gold Scalper v2.0.3" in mq5
    assert "#include <Trade/Trade.mqh>" in mq5
    assert "trade.BuyStop" in mq5
    assert "trade.SellStop" in mq5
    assert "InpMagic            = 30250003" in mq5
    assert "InpTrailStartUsd    = 0.50" in mq5
    assert "InpTrailDistanceUsd = 0.70" in mq5
    assert "InpTrailStepUsd     = 0.10" in mq5
    assert "InpManageManual     = true" in mq5
    assert "InpPauseAutoWhenManual = true" in mq5
    assert "InpManualKeepStops  = true" in mq5
    assert "ORDER_TYPE_BUY_LIMIT" in mq5
    assert "ORDER_TYPE_SELL_LIMIT" in mq5
    assert "ORDER_TYPE_BUY_STOP" in mq5
    assert "HasManualExposure" in mq5
    assert "ApplyTrail" in mq5
    assert "GOLD#" in mq5 or "XAUUSD" in mq5
    assert mq5.count("#include") == 1


def test_ea_forbids_grid_and_martingale():
    mq5 = EA.read_text(encoding="utf-8")
    low = mq5.lower()
    assert "no grid" in low
    assert "no martingale" in low
    assert "no averaging" in low
    assert "OrderSend" not in mq5
    assert "InpMartingale" not in mq5
    assert "gridLot" not in mq5
    assert "InpGrid" not in mq5


def test_manual_fill_keeps_user_stops_and_trails():
    mq5 = EA.read_text(encoding="utf-8")
    assert "IsManualPosition" in mq5
    assert "InpManualKeepStops" in mq5
    assert "your SL/TP kept" in mq5.lower() or "your SL/TP" in mq5
    assert "DeleteAllPendings" in mq5
    assert "IsOurOrder" in mq5
    setup = SETUP.read_text(encoding="utf-8")
    assert "V2.0.3" in setup
    assert "$0.50" in setup
    assert "$0.70" in setup
    assert "BUY STOP" in setup
    assert "SELL STOP" in setup
    assert "LIMIT" in setup


def test_usd_trail_points_match_gold_001_lot():
    assert usd_to_points(0.50) == DEF_TRAIL_START_PTS
    assert usd_to_points(0.70) == DEF_TRAIL_DISTANCE_PTS
    assert usd_to_points(0.10) == DEF_TRAIL_STEP_PTS
    start, dist, step = default_trail_points()
    assert start == 50
    assert dist == 70
    assert step == 10
    assert DEF_TRAIL_START_USD == 0.50
    assert DEF_TRAIL_DISTANCE_USD == 0.70
    assert DEF_TRAIL_STEP_USD == 0.10


def test_trail_starts_at_fifty_cents_with_original_distance():
    open_px = 2000.0
    user_sl = 1990.0
    # +$0.40: not yet
    assert apply_trail(True, 2000.40, 2000.42, open_px, user_sl, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10) == user_sl
    # +$0.50: trail 0.70 behind bid -> 1999.80 (below BE, original Thunder distance)
    sl = apply_trail(True, 2000.50, 2000.52, open_px, user_sl, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10)
    assert abs(sl - 1999.80) < 1e-9
    # follow price
    sl2 = apply_trail(True, 2001.20, 2001.22, open_px, sl, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10)
    assert abs(sl2 - 2000.50) < 1e-9
    # do not loosen
    sl3 = apply_trail(True, 2000.90, 2000.92, open_px, sl2, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10)
    assert sl3 == sl2


def test_sell_trail_and_keep_tighter_user_sl():
    open_px = 2000.0
    user_sl = 2010.0
    sl = apply_trail(False, 1999.48, 1999.50, open_px, user_sl, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10)
    assert abs(sl - 2000.20) < 1e-9
    tight = 1999.40
    kept = apply_trail(False, 1999.48, 1999.50, open_px, tight, trail_start_pts=50, trail_dist_pts=70, trail_step_pts=10)
    assert kept == tight


def test_manual_pending_and_pause_auto():
    assert is_manual_pending(0, "GOLD#", "BUY_STOP") is True
    assert is_manual_pending(0, "GOLD#", "SELL_LIMIT") is True
    assert is_manual_pending(EA_MAGIC, "GOLD#", "BUY_STOP") is False
    assert is_manual_pending(0, "EURUSD", "BUY_STOP") is False
    assert is_manual_position(0, "GOLD#") is True
    assert is_manual_position(EA_MAGIC, "GOLD#") is False
    assert has_manual_exposure([], [{"magic": 0, "symbol": "GOLD#", "type": "BUY_STOP"}]) is True
    assert has_manual_exposure([{"magic": 0, "symbol": "GOLD#"}], []) is True
    assert has_manual_exposure([{"magic": EA_MAGIC, "symbol": "GOLD#"}], []) is False
    assert pause_auto_when_manual(has_manual=True) is True
    assert pause_auto_when_manual(has_manual=False) is False
    assert pause_auto_when_manual(pause=False, has_manual=True) is False


def test_m15_unbroken_swing_and_session():
    highs = [2001.0, 2000.5, 2000.2, 1999.0, 1998.5, 1998.0, 2002.0, 1997.0, 1996.5, 1996.0, 1995.5, 1995.0]
    # index 6 = 2002 is a 5-bar swing high but later bars (0..5) did not exceed 2002
    # strength 1 for a tiny fixture
    tiny_high = [2010.0, 2005.0, 2012.0, 2004.0, 2003.0]
    assert swing_unbroken(True, tiny_high, strength=1) == 2012.0
    tiny_broken = [2013.0, 2005.0, 2012.0, 2004.0, 2003.0]
    assert swing_unbroken(True, tiny_broken, strength=1) is None
    tiny_low = [1990.0, 1995.0, 1988.0, 1996.0, 1997.0]
    assert swing_unbroken(False, tiny_low, strength=1) == 1988.0
    assert stop_entry(1, 2012.0, 2010.0, buffer=0.50, min_gap=0.20) == 2012.50
    assert stop_entry(-1, 1988.0, 1990.0, buffer=0.50, min_gap=0.20) == 1987.50
    assert stop_entry(1, 2012.0, 2012.40, buffer=0.50, min_gap=0.20) == 0.0
    assert in_session(8) is True
    assert in_session(21) is False
    assert in_session(7) is False
    assert highs[6] == 2002.0


def test_pack_zip_is_single_file_ea():
    assert ZIP.is_file()
    with zipfile.ZipFile(ZIP) as zf:
        names = set(zf.namelist())
        setup = zf.read("SETUP.txt").decode("utf-8")
        ea = zf.read("Experts/JM_THUNDER_GOLD_SCALPER.mq5").decode("utf-8")
    assert "Experts/JM_THUNDER_GOLD_SCALPER.mq5" in names
    assert "SETUP.txt" in names
    assert not any(n.endswith(".mqh") for n in names)
    assert "V2.0.3" in setup
    assert '#property version   "2.03"' in ea
    assert "InpTrailStartUsd    = 0.50" in ea
