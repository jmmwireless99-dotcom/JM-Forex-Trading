"""Lab strategy unit tests — original 4-pair presets."""

from __future__ import annotations

from app.strategy import evaluate_mean_revert, evaluate_strategy


def _m5_candles(
    *,
    count: int,
    base: float = 1.0800,
    span: float = 0.0010,
    close_at: str = "mid",
) -> list[dict]:
    candles = []
    lo = base
    hi = base + span
    for i in range(count):
        t = 1_700_000_000 + i * 300
        if close_at == "bottom":
            o, c = hi, lo + span * 0.05
        elif close_at == "top":
            o, c = lo, hi - span * 0.05
        else:
            o, c = lo + span * 0.4, lo + span * 0.5
        candles.append(
            {
                "time": t,
                "open": o,
                "high": hi,
                "low": lo,
                "close": c,
            }
        )
    return candles


def test_eurchf_mean_revert_signals_at_range_bottom():
    candles = _m5_candles(count=60, base=0.9400, span=0.0010, close_at="bottom")
    signal, block = evaluate_strategy("MEAN_REVERT", candles, symbol="EURCHF")
    assert block is None
    assert signal is not None
    assert signal.side == "BUY"


def test_eurusd_scalp_needs_enough_bars():
    candles = _m5_candles(count=30)
    _, block = evaluate_strategy("EMA_RSI_SCALP", candles, symbol="EURUSD")
    assert block is not None
    assert "Need" in block


def test_xauusd_trend_needs_55_bars_not_210():
    candles = _m5_candles(count=50, base=2400.0, span=5.0)
    _, block = evaluate_strategy("EMA_RSI_TREND", candles, symbol="XAUUSD")
    assert block is not None
    assert "55" in block
    assert "210" not in block


def test_mean_revert_mid_range_blocks():
    candles = _m5_candles(count=60, base=0.9400, span=0.0010, close_at="mid")
    _, block = evaluate_mean_revert(candles, symbol="EURCHF", lookback=36, edge_pct=0.22)
    assert block is not None
    assert "Mid-range" in block
