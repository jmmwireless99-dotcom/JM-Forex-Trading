"""XAUUSD lab — no strict EMA200 gold review preset."""

from app.strategy import evaluate_strategy


def test_gold_review_preset_not_used():
    candles = [{"time": i * 300, "open": 1, "high": 2, "low": 0, "close": 1} for i in range(60)]
    _, block = evaluate_strategy("EMA_RSI_TREND", candles, symbol="XAUUSD")
    assert block is not None
    assert "EMA200" not in (block or "")
    assert "Signal candle too small" not in (block or "")
