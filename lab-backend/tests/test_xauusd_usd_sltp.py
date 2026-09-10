"""XAUUSD lab — fixed USD stop/target (not pip-based)."""

from app.auto import _levels_for_auto
from app.broker import LabBroker
from app.pair_strategies import preset_for


def test_xauusd_preset_uses_usd_targets():
    p = preset_for("XAUUSD")
    assert p["sl_usd"] == 3.0
    assert p["tp_usd"] == 5.0
    assert "sl_pips" not in p


def test_usd_distance_at_003_lots():
    # 0.03 lots × $100/oz = $3 per $1.00 gold move
    dist = LabBroker.price_distance_for_usd("XAUUSD", 3.0, 0.03)
    assert abs(dist - 1.0) < 1e-9
    dist_tp = LabBroker.price_distance_for_usd("XAUUSD", 5.0, 0.03)
    assert abs(dist_tp - (5.0 / 3.0)) < 1e-9


def test_buy_levels_sl3_tp5_usd():
    preset = preset_for("XAUUSD")
    entry = 4400.0
    sl, tp = _levels_for_auto("BUY", entry, "XAUUSD", 0.03, preset, 50, 50)
    assert sl == 4399.0
    assert abs(tp - (4400.0 + 5.0 / 3.0)) < 1e-6


def test_sell_levels_sl3_tp5_usd():
    preset = preset_for("XAUUSD")
    entry = 4400.0
    sl, tp = _levels_for_auto("SELL", entry, "XAUUSD", 0.03, preset, 50, 50)
    assert sl == 4401.0
    assert abs(tp - (4400.0 - 5.0 / 3.0)) < 1e-6


def test_broker_pnl_matches_usd_targets():
    b = LabBroker(deposit=10_000)
    b._ticks["XAUUSD"] = {"mid": 4400.0, "bid": 4399.875, "ask": 4400.125}
    entry = b.entry_price("XAUUSD", "BUY")
    sl_dist = LabBroker.price_distance_for_usd("XAUUSD", 3.0, 0.03)
    sl = entry - sl_dist
    b.open_market(
        symbol="XAUUSD",
        side="BUY",
        lots=0.03,
        stop_loss=sl,
        take_profit=entry + LabBroker.price_distance_for_usd("XAUUSD", 5.0, 0.03),
    )
    closed = b.update_tick("XAUUSD", sl)
    assert len(closed) == 1
    assert abs(closed[0].realized_pnl + 3.0) < 0.05
