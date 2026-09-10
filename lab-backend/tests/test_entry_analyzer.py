"""Entry analyzer — OK / WEAK / MALI on BUY vs SELL."""

from __future__ import annotations

from app.entry_analyzer import analyze_entry, hour_bias, required_score, verdict_for_side


def _trend_candles(
    *,
    count: int = 80,
    base: float = 2650.0,
    step: float = -0.8,
    small_prev: bool = True,
    break_side: str = "SELL",
) -> list[dict]:
    """Build a directional M5 series with a small candle then a breakout."""
    candles = []
    price = base
    t0 = 1_720_000_000  # ~2024-07-05 00:00 UTC
    for i in range(count):
        t = t0 + i * 300
        o = price
        c = price + step
        high = max(o, c) + 0.15
        low = min(o, c) - 0.15
        candles.append({"time": t, "open": o, "high": high, "low": low, "close": c})
        price = c

    # Rewrite last two bars: small indecision then directional close.
    prev = candles[-2]
    cur = candles[-1]
    mid = float(prev["close"])
    if small_prev:
        candles[-2] = {
            "time": prev["time"],
            "open": mid,
            "close": mid + 0.04,
            "high": mid + 0.12,
            "low": mid - 0.12,
        }
    if break_side == "SELL":
        candles[-1] = {
            "time": cur["time"],
            "open": mid,
            "close": mid - 1.6,
            "high": mid + 0.05,
            "low": mid - 1.7,
        }
    else:
        candles[-1] = {
            "time": cur["time"],
            "open": mid,
            "close": mid + 1.6,
            "high": mid + 1.7,
            "low": mid - 0.05,
        }
    return candles


def test_hour_bias_follows_v61_whitelist():
    assert hour_bias(5, symbol="XAUUSD") == "SELL"
    assert hour_bias(23, symbol="XAUUSD") == "BUY"
    assert hour_bias(16, symbol="XAUUSD") == "WORST"
    assert hour_bias(11, symbol="XAUUSD") == "WORST"
    assert hour_bias(11, symbol="EURUSD") == "NEUTRAL"


def test_against_hour_raises_required_score():
    aligned = required_score("SELL", "SELL")
    against = required_score("BUY", "SELL")
    assert against > aligned


def test_downtrend_sell_breakout_not_buy():
    candles = _trend_candles(step=-0.9, break_side="SELL")
    # Bar times land in hour 00 UTC → SELL bias
    result = analyze_entry(candles, symbol="XAUUSD", hour=5)
    buy = verdict_for_side(result, "BUY")
    sell = verdict_for_side(result, "SELL")
    assert buy.verdict == "MALI"
    assert sell.score >= buy.score


def test_uptrend_buy_stricter_in_sell_hour():
    candles = _trend_candles(step=0.9, break_side="BUY")
    result = analyze_entry(candles, symbol="XAUUSD", hour=5)
    buy = verdict_for_side(result, "BUY")
    assert buy.verdict == "MALI"
    assert any("strict-hour" in r or "SAFE-AB" in r for r in buy.reasons)
    assert result.hour_bias == "SELL"


def test_fat_candle_is_mali_not_setup():
    candles = _trend_candles(small_prev=False, break_side="SELL")
    # Make previous bar a full-body trend bar
    prev = candles[-2]
    candles[-2] = {
        "time": prev["time"],
        "open": float(prev["open"]),
        "close": float(prev["open"]) - 2.0,
        "high": float(prev["open"]) + 0.1,
        "low": float(prev["open"]) - 2.1,
    }
    result = analyze_entry(candles, symbol="XAUUSD", hour=5)
    sell = verdict_for_side(result, "SELL")
    assert sell.verdict == "MALI"
    assert any("small candle" in r for r in sell.reasons)
    assert sell.score < sell.required


def test_warmup_is_wait():
    candles = _trend_candles(count=20)
    result = analyze_entry(candles, symbol="XAUUSD", hour=11)
    assert result.verdict == "WAIT"
    assert result.preferred_side is None


def test_result_json_has_both_sides():
    candles = _trend_candles()
    result = analyze_entry(candles, symbol="XAUUSD", hour=5)
    data = result.to_dict()
    assert data["buy"]["side"] == "BUY"
    assert data["sell"]["side"] == "SELL"
    assert data["hour_bias"] == "SELL"
    assert "summary" in data
