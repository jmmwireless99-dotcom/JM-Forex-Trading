from app.risk.lot_sizing import lots_for_capital


def test_lots_per_1000_usd():
    assert lots_for_capital(1000) == 0.03
    assert lots_for_capital(2000) == 0.06
    assert lots_for_capital(10000) == 0.30
    assert lots_for_capital(500) == 0.01  # 0.015 rounds to 0.01 at 2dp
    assert lots_for_capital(0) == 0.01


def test_custom_rate():
    assert lots_for_capital(1000, lots_per_1000=0.05) == 0.05
