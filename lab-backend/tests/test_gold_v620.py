from app.gold_v620 import apply_required_score, h21_sell_blocked, strong_trend_score_adj


def test_h21_sell_only():
    assert h21_sell_blocked("SELL", 21) is True
    assert h21_sell_blocked("BUY", 21) is False
    assert h21_sell_blocked("SELL", 20) is False
    assert h21_sell_blocked("SELL", 21, enabled=False) is False


def test_strong_trend_boost_only_on_both_thresholds():
    assert strong_trend_score_adj(35.0, 8.0) == -1
    assert strong_trend_score_adj(34.9, 8.0) == 0
    assert strong_trend_score_adj(40.0, 7.9) == 0
    assert strong_trend_score_adj(40.0, 9.0, enabled=False) == 0


def test_required_score_floor_is_one():
    assert apply_required_score(1, 40.0, 10.0) == 1
    assert apply_required_score(3, 40.0, 10.0) == 2
    assert apply_required_score(3, 20.0, 3.0) == 3
