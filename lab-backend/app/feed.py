from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Yahoo FX / gold symbols
YAHOO = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
}

SUPPORTED = list(YAHOO.keys())

# Soft defaults when Yahoo throttles (updated from last good quote)
_FALLBACK = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2650,
    "XAUUSD": 2650.0,
}
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 8.0


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cached(symbol: str) -> dict[str, Any] | None:
    row = _CACHE.get(symbol)
    if not row:
        return None
    if time.monotonic() - row["_mono"] > _CACHE_TTL:
        return None
    return row


def fetch_quote(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    ysym = YAHOO.get(sym)
    if not ysym:
        raise ValueError(f"Unsupported symbol: {symbol}")

    hit = _cached(sym)
    if hit:
        return {k: v for k, v in hit.items() if k != "_mono"}

    params = urllib.parse.urlencode({"interval": "1m", "range": "1d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}"
    try:
        payload = _http_json(url)
    except Exception as e:
        log.warning("yahoo quote failed %s: %s", sym, e)
        stale = _CACHE.get(sym)
        if stale:
            out = {k: v for k, v in stale.items() if k != "_mono"}
            out["stale"] = True
            return out
        mid = _FALLBACK.get(sym)
        if mid is not None:
            return {
                "symbol": sym,
                "mid": float(mid),
                "source": "fallback",
                "stale": True,
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
        raise RuntimeError(f"Market feed unavailable for {sym}") from e
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"No quote for {sym}")
    meta = results[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        closes = ((results[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        price = next((c for c in reversed(closes) if c is not None), None)
    if price is None:
        raise RuntimeError(f"No price for {sym}")
    row = {
        "symbol": sym,
        "mid": float(price),
        "source": "yahoo",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "_mono": time.monotonic(),
    }
    _CACHE[sym] = row
    _FALLBACK[sym] = float(price)
    return {k: v for k, v in row.items() if k != "_mono"}


def fetch_candles(symbol: str, interval: str = "5m", limit: int = 120) -> dict[str, Any]:
    sym = symbol.upper()
    ysym = YAHOO.get(sym)
    if not ysym:
        raise ValueError(f"Unsupported symbol: {symbol}")
    y_int = {"1": "1m", "5": "5m", "15": "15m", "60": "60m"}.get(interval, interval)
    params = urllib.parse.urlencode({"interval": y_int, "range": "5d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}"
    payload = _http_json(url)
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"No candles for {sym}")
    row = results[0]
    timestamps = row.get("timestamp") or []
    quote = ((row.get("indicators") or {}).get("quote") or [{}])[0]
    candles = []
    for i, ts in enumerate(timestamps):
        o = quote.get("open", [None])[i] if i < len(quote.get("open", [])) else None
        h = quote.get("high", [None])[i] if i < len(quote.get("high", [])) else None
        l = quote.get("low", [None])[i] if i < len(quote.get("low", [])) else None
        c = quote.get("close", [None])[i] if i < len(quote.get("close", [])) else None
        if None in (o, h, l, c):
            continue
        candles.append(
            {"time": int(ts), "open": float(o), "high": float(h), "low": float(l), "close": float(c)}
        )
    if limit > 0:
        candles = candles[-limit:]
    return {"symbol": sym, "interval": y_int, "candles": candles}
