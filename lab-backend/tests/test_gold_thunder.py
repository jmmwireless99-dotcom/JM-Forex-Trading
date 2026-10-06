from pathlib import Path
import zipfile

from app.gold_thunder import (
    DEF_TRAIL_DISTANCE_PTS,
    DEF_TRAIL_DISTANCE_USD,
    DEF_TRAIL_START_PTS,
    DEF_TRAIL_START_USD,
    DEF_TRAIL_STEP_PTS,
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
    update_extreme,
    usd_to_points,
)

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "mt5" / "Experts" / "JM_THUNDER_GOLD_SCALPER_V7.mq5"
SETUP = ROOT / "mt5" / "JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt"
ZIP = ROOT / "releases" / "JM-THUNDER-GOLD-SCALPER-V7-Pack.zip"


def test_ea_is_v701_fast_trail():
    mq5 = EA.read_text(encoding="utf-8")
    assert '#property version   "7.01"' in mq5
    assert "JM Thunder GOLD Scalper V7.0" in mq5
    assert "InpFastTrail        = true" in mq5
    assert "InpFastEntry        = true" in mq5
    assert "InpTrailReplacesSL  = true" in mq5
    assert "InpTrailStepUsd     = 0.0" in mq5
    assert "UpdateTrailExtreme" in mq5
    assert "InpMagic            = 30250007" in mq5
    assert "InpTrailStartUsd    = 0.50" in mq5
    assert "InpTrailDistanceUsd = 0.70" in mq5
    assert "InpManageManual     = true" in mq5
    assert "InpPauseAutoWhenManual" not in mq5
    assert "trade.BuyStop" in mq5
    assert mq5.count("#include") == 1


def test_ea_forbids_grid_and_martingale():
    mq5 = EA.read_text(encoding="utf-8")
    low = mq5.lower()
    assert "no grid" in low
    assert "no martingale" in low
    assert "no averaging" in low
    assert "OrderSend" not in mq5
    assert "InpMartingale" not in mq5


def test_manual_and_setup_docs():
    mq5 = EA.read_text(encoding="utf-8")
    assert "IsManualPosition" in mq5
    setup = SETUP.read_text(encoding="utf-8")
    assert "V7.0" in setup
    assert "$0.50" in setup
    assert "$0.70" in setup
    assert "pitik" in setup.lower() or "fast" in setup.lower() or "extreme" in setup.lower()


def test_usd_trail_defaults():
    assert usd_to_points(0.50) == DEF_TRAIL_START_PTS
    assert usd_to_points(0.70) == DEF_TRAIL_DISTANCE_PTS
    start, dist, step = default_trail_points()
    assert start == 50
    assert dist == 70
    assert step == DEF_TRAIL_STEP_PTS
    assert DEF_TRAIL_START_USD == 0.50
    assert DEF_TRAIL_DISTANCE_USD == 0.70
    assert EA_MAGIC == 30250007


def test_trail_locks_spike_extreme_then_pullback():
    open_px = 2000.0
    user_sl = 1990.0
    # not yet
    assert apply_trail(True, 2000.40, 2000.42, open_px, user_sl, trail_start_pts=50, trail_dist_pts=70) == user_sl
    # pitik peak — arm trail at extreme
    extreme = update_extreme(True, 0.0, 2010.0, 2010.02)
    assert extreme == 2010.0
    sl = apply_trail(
        True, 2010.0, 2010.02, open_px, user_sl,
        trail_start_pts=50, trail_dist_pts=70, extreme=extreme,
    )
    assert abs(sl - (2010.0 - 0.70)) < 1e-9
    # pullback — do not loosen; keep lock at end of move
    extreme = update_extreme(True, extreme, 2008.0, 2008.02)
    assert extreme == 2010.0
    sl2 = apply_trail(
        True, 2008.0, 2008.02, open_px, sl,
        trail_start_pts=50, trail_dist_pts=70, extreme=extreme,
    )
    assert sl2 == sl


def test_trail_replaces_wide_initial_sl():
    open_px = 2000.0
    wide_sl = 1985.0
    sl = apply_trail(
        True, 2000.50, 2000.52, open_px, wide_sl,
        trail_start_pts=50, trail_dist_pts=70, extreme=2000.50,
        trail_replaces_sl=True,
    )
    assert abs(sl - 1999.80) < 1e-9
    assert sl > wide_sl


def test_sell_spike_extreme():
    open_px = 2000.0
    user_sl = 2010.0
    extreme = update_extreme(False, 0.0, 1990.0, 1990.0)
    assert extreme == 1990.0
    sl = apply_trail(
        False, 1990.0, 1990.0, open_px, user_sl,
        trail_start_pts=50, trail_dist_pts=70, extreme=extreme,
    )
    assert abs(sl - (1990.0 + 0.70)) < 1e-9
    # bounce up — keep lock
    extreme = update_extreme(False, extreme, 1992.0, 1992.0)
    assert extreme == 1990.0
    sl2 = apply_trail(
        False, 1992.0, 1992.0, open_px, sl,
        trail_start_pts=50, trail_dist_pts=70, extreme=extreme,
    )
    assert sl2 == sl


def test_manual_pending_auto_stays_on():
    assert is_manual_pending(0, "GOLD#", "BUY_STOP") is True
    assert is_manual_position(0, "GOLD#") is True
    assert has_manual_exposure([], [{"magic": 0, "symbol": "GOLD#", "type": "BUY_STOP"}]) is True
    assert pause_auto_when_manual(has_manual=True) is False


def test_m15_unbroken_swing_and_session():
    tiny_high = [2010.0, 2005.0, 2012.0, 2004.0, 2003.0]
    assert swing_unbroken(True, tiny_high, strength=1) == 2012.0
    assert stop_entry(1, 2012.0, 2010.0, buffer=0.50, min_gap=0.20) == 2012.50
    assert in_session(8) is True
    assert in_session(21) is False


def test_pack_zip_has_desktop_copy():
    assert ZIP.is_file()
    with zipfile.ZipFile(ZIP) as zf:
        names = set(zf.namelist())
        ea = zf.read("Experts/JM_THUNDER_GOLD_SCALPER_V7.mq5").decode("utf-8")
    assert "Experts/JM_THUNDER_GOLD_SCALPER_V7.mq5" in names
    assert "COPY-TO-DESKTOP.bat" in names
    assert "Desktop/JM_THUNDER_GOLD_SCALPER_V7.mq5" in names
    assert '#property version   "7.01"' in ea
    assert "InpFastTrail        = true" in ea
