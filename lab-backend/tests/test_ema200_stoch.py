from app.ema200_stoch import (
    ema200_side,
    favorable_price_move,
    is_small_candle,
    next_scale_action,
    nfp_friday_blocked,
    pullback_ok,
    scale_out_volumes,
    stoch_buy_cross,
    stoch_sell_cross,
)


def test_small_doji_rejected_by_min_range():
    assert is_small_candle(2000.0, 2000.05, 1999.98, 2000.02, min_range=0.20) is False


def test_small_indecision_passes():
    assert is_small_candle(2000.0, 2000.80, 1999.90, 2000.15) is True


def test_fat_candle_fails():
    assert is_small_candle(2000.0, 2001.0, 1999.9, 2000.95) is False


def test_ema_side():
    assert ema200_side(2651.0, 2650.0) == "BUY"
    assert ema200_side(2649.0, 2650.0) == "SELL"
    assert ema200_side(2650.0, 2650.0) is None


def test_stoch_buy_cross_from_oversold():
    assert stoch_buy_cross(12.0, 15.0, 22.0, 18.0) is True
    assert stoch_buy_cross(25.0, 24.0, 30.0, 22.0) is False


def test_stoch_sell_cross_from_overbought():
    assert stoch_sell_cross(88.0, 85.0, 79.0, 84.0) is True
    assert stoch_sell_cross(70.0, 72.0, 65.0, 68.0) is False


def test_buy_pullback_needs_small_red_bars():
    trig = {"open": 10.0, "high": 10.8, "low": 9.9, "close": 10.3}
    red1 = {"open": 10.40, "high": 10.50, "low": 10.00, "close": 10.22}
    red2 = {"open": 10.50, "high": 10.55, "low": 10.05, "close": 10.28}
    assert pullback_ok(1, [trig, red1, red2]) is True
    green = {"open": 10.20, "high": 10.80, "low": 10.10, "close": 10.55}
    assert pullback_ok(1, [trig, green, red2]) is False


def test_scale_out_003_three_legs():
    assert scale_out_volumes(0.03) == (0.01, 0.01, 0.01)


def test_scale_out_001_cannot_split():
    assert scale_out_volumes(0.01) == (0.0, 0.0, 0.01)


def test_nfp_first_friday_only():
    assert nfp_friday_blocked(4, 5, 15) is True
    assert nfp_friday_blocked(4, 12, 15) is False
    assert nfp_friday_blocked(3, 5, 15) is False


def test_scale_out_uses_gold_price_not_account_pnl():
    # 0.03 lot would already show ~$5 account P/L at only ~$1.67 price — ignore that.
    assert favorable_price_move("BUY", 2650.0, 2655.0, 2655.10) == 5.0
    assert next_scale_action(1.67) == "HOLD"
    assert next_scale_action(5.0) == "TP1"
    assert next_scale_action(10.0, did_tp1=True) == "TP2"
    assert next_scale_action(15.0, did_tp1=True, did_tp2=True) == "TP3"


def test_sell_favorable_move_uses_ask():
    assert favorable_price_move("SELL", 2650.0, 2644.90, 2645.0) == 5.0
