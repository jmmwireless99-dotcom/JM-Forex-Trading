"""Lab strategy unit tests — scalping presets for 4-pair suite."""

from __future__ import annotations

from app.strategy import evaluate_mean_revert, evaluate_strategy


def _m5_candles(
    *,
    count: int,
    base: float = 1.0800,
    span: float = 0.0010,
    close_at: str = "mid",
) -> list[dict]:
    """Build synthetic M5 candles with a configurable range span."""
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


def test_eurchf_mean_revert_allows_tight_asian_range():
    """EUR/CHF 7–10 pip ranges should not be blocked (was 18p min)."""
    # 10 pips = 0.0010 on EURCHF
    candles = _m5_candles(count=60, base=0.9400, span=0.0010, close_at="bottom")
    signal, block = evaluate_strategy("MEAN_REVERT", candles, symbol="EURCHF")
    assert block is None or "Range too tight" not in (block or ""), block
    # May still block on bar direction — that's OK; range gate must pass
    _, block_only = evaluate_mean_revert(
        candles,
        symbol="EURCHF",
        lookback=36,
        edge_pct=0.15,
        min_range_pips=8.0,
    )
    assert block_only is None or "Range too tight" not in block_only


def test_eurchf_mean_revert_blocks_flat_range():
    candles = _m5_candles(count=60, base=0.9400, span=0.0004, close_at="bottom")  # 4 pips
    _, block = evaluate_strategy("MEAN_REVERT", candles, symbol="EURCHF")
    assert block is not None
    assert "Range too tight" in block


def test_eurusd_scalp_needs_enough_bars():
    candles = _m5_candles(count=30)
    _, block = evaluate_strategy("EMA_RSI_SCALP", candles, symbol="EURUSD")
    assert block is not None
    assert "Need" in block


def test_xauusd_gold_needs_210_bars():
    candles = _m5_candles(count=150, base=2400.0, span=5.0)
    _, block = evaluate_strategy("EMA_RSI_TREND", candles, symbol="XAUUSD")
    assert block is not None
    assert "210" in block
