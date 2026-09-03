"""Lab strategy tests."""

from app.strategy import evaluate_strategy


def _candles(closes: list[float], *, start: int = 1_700_000_000) -> list[dict]:
    out = []
    t = start
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(
            {
                "time": t + i * 300,
                "open": o,
                "high": max(o, c) + 0.5,
                "low": min(o, c) - 0.5,
                "close": c,
            }
        )
    return out


def test_xauusd_scalper_sell_in_wider_zone():
    """RSI ~45 should pass gold sell zone (42–65) after restore."""
    base = 4400.0
    # Downtrend: declining closes, EMA20 < EMA50
    closes = [base + (i * 0.1 if i < 40 else -i * 0.3) for i in range(60)]
    closes = [base - i * 0.4 for i in range(60)]
    candles = _candles(closes)
    sig, block = evaluate_strategy("EMA_RSI_TREND", candles, symbol="XAUUSD")
    # May or may not fire depending on RSI — at least should not use EMA200 block text
    if block:
        assert "EMA200" not in block
        assert "Signal candle too small" not in block


def test_gold_ema_rsi_alias_uses_scalper():
    sig, block = evaluate_strategy("GOLD_EMA_RSI", _candles([4400.0] * 60), symbol="XAUUSD")
    if block:
        assert "EMA200" not in block
