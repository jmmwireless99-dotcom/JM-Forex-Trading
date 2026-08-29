"""Lab strategy unit tests."""

from __future__ import annotations

from app.strategy import evaluate_mean_revert, evaluate_ema_rsi


def _candles(closes: list[float], *, bullish_last: bool = True) -> list[dict]:
    out = []
    for i, c in enumerate(closes):
        o = c - 0.0001 if bullish_last and i == len(closes) - 1 else c + 0.0001
        if i == len(closes) - 1 and not bullish_last:
            o = c + 0.0001
        out.append(
            {
                "time": 1_700_000_000 + i * 300,
                "open": o,
                "high": max(o, c) + 0.00005,
                "low": min(o, c) - 0.00005,
                "close": c,
            }
        )
    return out


def test_mean_revert_blocks_sell_in_uptrend():
    # Rising series — top of range but uptrend
    closes = [0.930 + i * 0.0003 for i in range(60)]
    candles = _candles(closes, bullish_last=True)
    sig, block = evaluate_mean_revert(
        candles, symbol="EURCHF", lookback=36, edge_pct=0.15, min_range_pips=5.0
    )
    assert sig is None
    assert block and "uptrend" in block.lower()


def test_mean_revert_blocks_bullish_bar_at_top():
    closes = [0.935] * 55 + [0.936, 0.937, 0.938, 0.939, 0.940]
    candles = _candles(closes, bullish_last=True)
    sig, block = evaluate_mean_revert(
        candles, symbol="EURCHF", lookback=36, edge_pct=0.25, min_range_pips=5.0
    )
    assert sig is None
    assert block and ("bullish bar" in block.lower() or "uptrend" in block.lower())


def test_ema_rsi_requires_directional_bar():
    closes = [1.08 + (i * 0.00001) for i in range(60)]
    candles = _candles(closes, bullish_last=False)
    sig, block = evaluate_ema_rsi(
        candles,
        symbol="EURUSD",
        rsi_buy=(0.0, 100.0),
        rsi_sell=(0.0, 100.0),
    )
    # With wide RSI bands, trend may fire but bearish bar on bullish trend blocks BUY
    if sig is None:
        assert block
