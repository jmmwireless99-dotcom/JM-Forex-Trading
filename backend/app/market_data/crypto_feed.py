"""Live BTCUSD mid / candles via Binance BTCUSDT (paper desk sync)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_SYMBOL = "BTCUSDT"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 15.0
_PRICE_CACHE: tuple[float, float] | None = None  # (ts, price)


def _http_json(url: str, timeout: float = 12) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_btc_price() -> float | None:
    """Latest BTCUSDT mid for paper sync."""
    global _PRICE_CACHE
    now = time.time()
    if _PRICE_CACHE and now - _PRICE_CACHE[0] < _CACHE_TTL_SEC:
        return _PRICE_CACHE[1]
    try:
        url = f"{BINANCE_TICKER}?symbol={BINANCE_SYMBOL}"
        payload = _http_json(url, timeout=8)
        price = float(payload["price"])
        if 1000 < price < 1_000_000:
            _PRICE_CACHE = (now, price)
            return price
    except Exception as exc:  # noqa: BLE001
        logger.warning("btc ticker failed: %s", exc)
    return _PRICE_CACHE[1] if _PRICE_CACHE else None


def fetch_btc_candles(interval: str = "5m", limit: int = 300) -> dict[str, Any]:
    """OHLC for dashboard / warmup (Binance BTCUSDT)."""
    key = f"{interval}:{limit}"
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL_SEC:
        return hit[1]

    iv = interval if interval in {"1m", "5m", "15m", "30m", "1h", "4h", "1d"} else "5m"
    params = urllib.parse.urlencode(
        {"symbol": BINANCE_SYMBOL, "interval": iv, "limit": min(max(limit, 50), 1000)}
    )
    url = f"{BINANCE_KLINES}?{params}"
    try:
        rows = _http_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Binance BTC feed failed: {exc}") from exc

    candles: list[dict[str, Any]] = []
    for row in rows:
        candles.append(
            {
                "time": int(row[0] // 1000),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
        )
    price = candles[-1]["close"] if candles else fetch_btc_price()
    out = {
        "symbol": "BTCUSD",
        "source": "binance:BTCUSDT",
        "interval": iv,
        "price": price,
        "candles": candles,
    }
    _CACHE[key] = (now, out)
    return out
