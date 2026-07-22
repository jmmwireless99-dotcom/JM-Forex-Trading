"""Fetch live gold OHLC (COMEX GC=F via Yahoo) for dashboard display."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_CHART_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# COMEX gold futures — tracks spot closely; free Yahoo feed (no API key).
DEFAULT_SYMBOL = "GC=F"

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 20.0

INTERVAL_MAP = {
    "1": "1m",
    "1m": "1m",
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
    "30": "30m",
    "30m": "30m",
    "60": "60m",
    "1h": "60m",
    "240": "1h",
    "D": "1d",
    "1d": "1d",
}


def _yahoo_range_for_interval(interval: str) -> str:
    if interval in {"1m"}:
        return "1d"
    if interval in {"5m", "15m"}:
        return "5d"
    if interval in {"30m", "60m", "1h"}:
        return "1mo"
    return "3mo"


def fetch_gold_candles(
    *,
    interval: str = "5m",
    symbol: str = DEFAULT_SYMBOL,
    limit: int = 300,
) -> dict[str, Any]:
    import time

    y_interval = INTERVAL_MAP.get(str(interval), "5m")
    cache_key = f"{symbol}:{y_interval}:{limit}"
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit and now - hit[0] < _CACHE_TTL_SEC:
        return hit[1]

    y_range = _yahoo_range_for_interval(y_interval)
    params = urllib.parse.urlencode({"interval": y_interval, "range": y_range})
    urls = [
        f"{YAHOO_CHART.format(symbol=urllib.parse.quote(symbol))}?{params}",
        f"{YAHOO_CHART_ALT.format(symbol=urllib.parse.quote(symbol))}?{params}",
    ]
    payload = None
    last_err: Exception | None = None
    for url in urls:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            logger.warning("gold feed attempt failed: %s", e)
            continue
    if payload is None:
        raise RuntimeError(f"Yahoo gold feed failed: {last_err}") from last_err

    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        err = (payload.get("chart") or {}).get("error") or {"description": "no data"}
        raise RuntimeError(err.get("description") or "no gold candle data")

    row = results[0]
    meta = row.get("meta") or {}
    timestamps = row.get("timestamp") or []
    quote = ((row.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []

    candles: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = (
            opens[i] if i < len(opens) else None,
            highs[i] if i < len(highs) else None,
            lows[i] if i < len(lows) else None,
            closes[i] if i < len(closes) else None,
        )
        if o is None or h is None or l is None or c is None:
            continue
        candles.append(
            {
                "time": int(ts),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "open_time": datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(),
            }
        )

    if limit > 0:
        candles = candles[-limit:]

    last = candles[-1] if candles else None
    out = {
        "ok": True,
        "source": "yahoo",
        "symbol": meta.get("symbol") or symbol,
        "label": "Gold futures (GC=F) · live market",
        "interval": y_interval,
        "price": meta.get("regularMarketPrice") or (last["close"] if last else None),
        "currency": meta.get("currency") or "USD",
        "exchange": meta.get("exchangeName") or "COMEX",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "candles": candles,
    }
    _CACHE[cache_key] = (now, out)
    return out
