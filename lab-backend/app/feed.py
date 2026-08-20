from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

YAHOO = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
}

BINANCE = {
    "EURUSD": "EURUSDT",
    "GBPUSD": "GBPUSDT",
    "XAUUSD": "PAXGUSDT",
}

BINANCE_API = "https://data-api.binance.vision/api/v3"
KRAKEN_PAIR = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD"}

SUPPORTED = list(YAHOO.keys())

INTERVAL_MAP = {
    "1": "5m",
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
    "60": "1h",
    "60m": "1h",
    "1h": "1h",
}

BINANCE_INTERVAL = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
}

_QUOTE_CACHE: dict[str, dict[str, Any]] = {}
_CANDLE_CACHE: dict[str, dict[str, Any]] = {}
_FALLBACK_MID = {"EURUSD": 1.0850, "GBPUSD": 1.2650, "XAUUSD": 2650.0}

_QUOTE_TTL = 18.0
_CANDLE_TTL = 90.0
_MIN_YAHOO_GAP = 2.8
_last_yahoo_at = 0.0
_lock = threading.Lock()


def _http_json(url: str, timeout: float = 12) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _throttle_yahoo() -> None:
    global _last_yahoo_at
    with _lock:
        wait = _MIN_YAHOO_GAP - (time.monotonic() - _last_yahoo_at)
        if wait > 0:
            time.sleep(wait)
        _last_yahoo_at = time.monotonic()


def _yahoo_chart(symbol: str, y_interval: str, y_range: str) -> dict[str, Any]:
    ysym = YAHOO[symbol]
    params = urllib.parse.urlencode({"interval": y_interval, "range": y_range})
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}",
    ]
    last_err: Exception | None = None
    for url in urls:
        try:
            _throttle_yahoo()
            return _http_json(url)
        except Exception as e:
            last_err = e
            log.warning("yahoo chart %s failed: %s", symbol, e)
    raise RuntimeError(str(last_err or "yahoo unavailable"))


def _parse_yahoo_candles(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError("no yahoo candle data")
    row = results[0]
    timestamps = row.get("timestamp") or []
    quote = ((row.get("indicators") or {}).get("quote") or [{}])[0]
    candles: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        o = quote.get("open", [None])[i] if i < len(quote.get("open", [])) else None
        h = quote.get("high", [None])[i] if i < len(quote.get("high", [])) else None
        l = quote.get("low", [None])[i] if i < len(quote.get("low", [])) else None
        c = quote.get("close", [None])[i] if i < len(quote.get("close", [])) else None
        if None in (o, h, l, c):
            continue
        candles.append({"time": int(ts), "open": float(o), "high": float(h), "low": float(l), "close": float(c)})
    if limit > 0:
        candles = candles[-limit:]
    return candles


def _binance_klines(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    bsym = BINANCE[symbol]
    b_int = BINANCE_INTERVAL.get(interval, interval)
    params = urllib.parse.urlencode(
        {"symbol": bsym, "interval": b_int, "limit": min(max(limit, 50), 1000)}
    )
    rows = _http_json(f"{BINANCE_API}/klines?{params}")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"binance klines empty for {bsym}")
    candles: list[dict[str, Any]] = []
    for row in rows:
        ts = int(row[0]) // 1000
        candles.append(
            {
                "time": ts,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
        )
    return candles


def _kraken_klines(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    pair = KRAKEN_PAIR.get(symbol)
    if not pair:
        raise ValueError(f"kraken unsupported: {symbol}")
    k_int = {"5m": 5, "15m": 15, "1h": 60}.get(interval, 5)
    data = _http_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={k_int}")
    result = data.get("result") or {}
    keys = [k for k in result if k != "last"]
    if not keys:
        raise RuntimeError(f"kraken no data for {pair}")
    rows = result[keys[0]]
    candles: list[dict[str, Any]] = []
    for row in rows:
        candles.append(
            {
                "time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
        )
    if limit > 0:
        candles = candles[-limit:]
    return candles


def _binance_price(symbol: str) -> float:
    bsym = BINANCE[symbol]
    data = _http_json(f"{BINANCE_API}/ticker/price?symbol={bsym}")
    return float(data["price"])


def _yahoo_range(interval: str) -> str:
    if interval in {"5m", "15m"}:
        return "5d"
    if interval in {"1h", "60m"}:
        return "1mo"
    return "5d"


def _stale_quote(symbol: str) -> dict[str, Any] | None:
    row = _QUOTE_CACHE.get(symbol)
    if not row:
        return None
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    out["stale"] = True
    return out


def fetch_quote(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    if sym not in YAHOO:
        raise ValueError(f"Unsupported symbol: {symbol}")

    row = _QUOTE_CACHE.get(sym)
    if row and time.monotonic() - row["_mono"] < _QUOTE_TTL:
        return {k: v for k, v in row.items() if not k.startswith("_")}

    mid: float | None = None
    source = "binance"

    try:
        mid = _binance_price(sym)
    except Exception as e:
        log.warning("binance quote %s: %s", sym, e)

    if mid is None:
        try:
            payload = _yahoo_chart(sym, "1m", "1d")
            results = (payload.get("chart") or {}).get("result") or []
            if results:
                meta = results[0].get("meta") or {}
                price = meta.get("regularMarketPrice")
                if price is None:
                    closes = ((results[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
                    price = next((c for c in reversed(closes) if c is not None), None)
                if price is not None:
                    mid = float(price)
                    source = "yahoo"
        except Exception as e:
            log.warning("yahoo quote %s: %s", sym, e)

    if mid is None:
        stale = _stale_quote(sym)
        if stale:
            return stale
        mid = _FALLBACK_MID.get(sym)
        if mid is None:
            raise RuntimeError(f"Market feed unavailable for {sym}")
        source = "fallback"

    out = {
        "symbol": sym,
        "mid": float(mid),
        "source": source,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "_mono": time.monotonic(),
    }
    _QUOTE_CACHE[sym] = out
    _FALLBACK_MID[sym] = float(mid)
    return {k: v for k, v in out.items() if not k.startswith("_")}


def fetch_candles(symbol: str, interval: str = "5m", limit: int = 120) -> dict[str, Any]:
    sym = symbol.upper()
    if sym not in YAHOO:
        raise ValueError(f"Unsupported symbol: {symbol}")

    y_int = INTERVAL_MAP.get(str(interval), interval)
    cache_key = f"{sym}:{y_int}:{limit}"
    cached = _CANDLE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached["_mono"] < _CANDLE_TTL:
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    candles: list[dict[str, Any]] = []
    source = "binance"
    errors: list[str] = []

    try:
        candles = _binance_klines(sym, y_int, limit)
    except Exception as e:
        errors.append(str(e))
        log.warning("binance candles %s %s: %s", sym, y_int, e)

    if not candles and sym in KRAKEN_PAIR:
        try:
            candles = _kraken_klines(sym, y_int, limit)
            source = "kraken"
        except Exception as e:
            errors.append(str(e))
            log.warning("kraken candles %s %s: %s", sym, y_int, e)

    if not candles:
        try:
            payload = _yahoo_chart(sym, y_int, _yahoo_range(y_int))
            candles = _parse_yahoo_candles(payload, limit)
            source = "yahoo"
        except Exception as e:
            errors.append(str(e))
            log.warning("yahoo candles %s %s: %s", sym, y_int, e)

    if not candles and cached:
        stale = {k: v for k, v in cached.items() if not k.startswith("_")}
        stale["stale"] = True
        stale["note"] = "Showing cached candles (feed rate limited)"
        return stale

    if not candles:
        raise RuntimeError(f"Candle feed unavailable for {sym}: {' | '.join(errors)}")

    out = {
        "symbol": sym,
        "interval": y_int,
        "source": source,
        "candles": candles,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "_mono": time.monotonic(),
    }
    _CANDLE_CACHE[cache_key] = out
    return {k: v for k, v in out.items() if not k.startswith("_")}
