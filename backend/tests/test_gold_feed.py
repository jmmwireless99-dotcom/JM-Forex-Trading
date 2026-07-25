import pytest

from app.market_data.gold_feed import INTERVAL_MAP, _yahoo_range_for_interval, fetch_gold_candles


def test_interval_map_defaults():
    assert INTERVAL_MAP["5"] == "5m"
    assert INTERVAL_MAP["60"] == "60m"
    assert _yahoo_range_for_interval("5m") == "5d"


def test_fetch_gold_candles_live():
    try:
        data = fetch_gold_candles(interval="5m", limit=50)
    except RuntimeError as e:
        msg = str(e)
        if any(x in msg for x in ("429", "451", "unavailable", "Forbidden")):
            pytest.skip(f"External gold feed blocked in this environment: {e}")
        raise
    assert data["ok"] is True
    assert data["source"] in {"yahoo", "binance"}
    assert data["symbol"]
    assert len(data["candles"]) >= 10
    c = data["candles"][-1]
    assert c["high"] >= c["low"]
    assert c["open"] > 0
    assert data["price"] > 1000
