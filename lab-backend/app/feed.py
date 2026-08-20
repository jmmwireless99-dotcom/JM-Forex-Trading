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
    "AUDNZD": "AUDNZD=X",
    "EURCHF": "EURCHF=X",
}

BINANCE = {
    "EURUSD": "EURUSDT",
    "GBPUSD": "GBPUSDT",
    "XAUUSD": "PAXGUSDT",
}

BINANCE_API = "https://data-api.binance.vision/api/v3"
KRAKEN_PAIR = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "EURCHF": "EURCHF", "AUDUSD": "AUDUSD"}
# AUD/NZD built from AUD/USD (Kraken) ÷ NZD/USD (Yahoo) — avoids Yahoo AUDNZD rate limits
CROSS_PAIRS = {"AUDNZD": ("AUDUSD", "NZDUSD")}
YAHOO_LEG = {"NZDUSD": "NZDUSD=X"}
YAHOO_ONLY: set[str] = set()

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
_FALLBACK_MID = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2650,
    "XAUUSD": 2650.0,
    "AUDNZD": 1.0800,
    "EURCHF": 0.9350,
}

_QUOTE_TTL = 18.0
_CANDLE_TTL = 90.0
_CROSS_CANDLE_TTL = 120.0
ER_API = "https://open.er-api.com/v6/latest/USD"
_NZDUSD_SPOT_CACHE: tuple[float, float] | None = None  # (monotonic, nzd/usd rate)
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


def _nzdusd_spot() -> float:
    """NZD/USD spot via open.er-api.com (cached 5 min)."""
    global _NZDUSD_SPOT_CACHE
    now = time.monotonic()
    if _NZDUSD_SPOT_CACHE and now - _NZDUSD_SPOT_CACHE[0] < 300:
        return _NZDUSD_SPOT_CACHE[1]
    data = _http_json(ER_API)
    if data.get("result") != "success":
        raise RuntimeError("er-api failed")
    nzd_per_usd = float(data["rates"]["NZD"])
    if nzd_per_usd <= 0:
        raise RuntimeError("invalid NZD rate")
    nzd_usd = 1.0 / nzd_per_usd
    _NZDUSD_SPOT_CACHE = (now, nzd_usd)
    return nzd_usd


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
    if symbol not in BINANCE:
        raise ValueError(f"no binance symbol for {symbol}")
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


def _yahoo_leg_candles(leg: str, y_interval: str, limit: int) -> list[dict[str, Any]]:
    """Fetch a Yahoo symbol used as a cross leg (e.g. NZDUSD=X)."""
    if leg not in YAHOO_LEG:
        raise ValueError(f"unknown yahoo leg {leg}")
    ysym = YAHOO_LEG[leg]
    cache_key = f"_leg:{leg}:{y_interval}:{limit}"
    cached = _CANDLE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached["_mono"] < _CROSS_CANDLE_TTL:
        return list(cached["candles"])

    params = urllib.parse.urlencode({"interval": y_interval, "range": _yahoo_range(y_interval)})
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{params}",
    ]
    last_err: Exception | None = None
    payload = None
    for url in urls:
        try:
            _throttle_yahoo()
            payload = _http_json(url)
            break
        except Exception as e:
            last_err = e
            log.warning("yahoo leg %s failed: %s", leg, e)
    if payload is None:
        if cached:
            return list(cached["candles"])
        raise RuntimeError(str(last_err or f"yahoo leg {leg} unavailable"))

    candles = _parse_yahoo_candles(payload, limit)
    _CANDLE_CACHE[cache_key] = {"candles": candles, "_mono": time.monotonic()}
    return candles


def _cross_candles(base: str, quote: str, interval: str, limit: int) -> list[dict[str, Any]]:
    """Build cross rate candles e.g. AUD/NZD = AUD/USD ÷ NZD/USD."""
    y_int = INTERVAL_MAP.get(str(interval), interval)

    if base == "AUDUSD" and base in KRAKEN_PAIR:
        leg_a = _kraken_klines("AUDUSD", y_int, limit + 10)
    elif base in BINANCE:
        leg_a = _binance_klines(base, y_int, limit + 10)
    else:
        raise RuntimeError(f"no feed for cross leg {base}")

    leg_b: list[dict[str, Any]] = []
    nzd_spot: float | None = None

    if quote in YAHOO_LEG:
        try:
            leg_b = _yahoo_leg_candles(quote, y_int, limit + 10)
        except Exception as e:
            log.warning("yahoo leg %s fallback to spot: %s", quote, e)

    if not leg_b and quote == "NZDUSD":
        nzd_spot = _nzdusd_spot()

    if leg_b:
        by_b = {int(c["time"]): c for c in leg_b}
        merged: list[dict[str, Any]] = []
        for a in leg_a:
            t = int(a["time"])
            b = by_b.get(t)
            if not b:
                continue
            bn_o, bn_h, bn_l, bn_c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
            if min(bn_o, bn_h, bn_l, bn_c) <= 0:
                continue
            merged.append(
                {
                    "time": t,
                    "open": float(a["open"]) / bn_o,
                    "high": max(float(a["high"]) / bn_l, float(a["low"]) / bn_h),
                    "low": min(float(a["low"]) / bn_h, float(a["high"]) / bn_l),
                    "close": float(a["close"]) / bn_c,
                }
            )
    elif nzd_spot is not None:
        merged = [
            {
                "time": int(a["time"]),
                "open": float(a["open"]) / nzd_spot,
                "high": float(a["high"]) / nzd_spot,
                "low": float(a["low"]) / nzd_spot,
                "close": float(a["close"]) / nzd_spot,
            }
            for a in leg_a
        ]
    else:
        raise RuntimeError(f"no feed for cross leg {quote}")

    if limit > 0:
        merged = merged[-limit:]
    if len(merged) < 20:
        raise RuntimeError(f"cross {base}/{quote} too few bars ({len(merged)})")
    return merged


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
    if symbol not in BINANCE:
        raise ValueError(f"no binance symbol for {symbol}")
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
    source = "yahoo"

    if sym in BINANCE:
        try:
            mid = _binance_price(sym)
            source = "binance"
        except Exception as e:
            log.warning("binance quote %s: %s", sym, e)

    if mid is None and sym in CROSS_PAIRS:
        try:
            base, quote = CROSS_PAIRS[sym]
            if base in KRAKEN_PAIR:
                a = _kraken_klines(base, "5m", 1)[-1]["close"]
            else:
                a = _binance_price(base)
            if quote in YAHOO_LEG:
                try:
                    q = _yahoo_leg_candles(quote, "5m", 1)[-1]["close"]
                except Exception:
                    q = _nzdusd_spot()
            else:
                q = _kraken_klines(quote, "5m", 1)[-1]["close"]
            if q > 0:
                mid = float(a) / float(q)
                source = "cross"
        except Exception as e:
            log.warning("cross quote %s: %s", sym, e)

    if mid is None and sym not in BINANCE:
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

    if mid is None and sym in KRAKEN_PAIR:
        try:
            candles = _kraken_klines(sym, "5m", 1)
            if candles:
                mid = candles[-1]["close"]
                source = "kraken"
        except Exception as e:
            log.warning("kraken quote %s: %s", sym, e)

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
    ttl = _CROSS_CANDLE_TTL if sym in CROSS_PAIRS else _CANDLE_TTL
    if cached and time.monotonic() - cached["_mono"] < ttl:
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    candles: list[dict[str, Any]] = []
    source = "binance"
    errors: list[str] = []

    if sym in CROSS_PAIRS:
        try:
            base, quote = CROSS_PAIRS[sym]
            candles = _cross_candles(base, quote, y_int, limit)
            source = "cross"
        except Exception as e:
            errors.append(str(e))
            log.warning("cross candles %s: %s", sym, e)

    if not candles and sym in BINANCE:
        try:
            candles = _binance_klines(sym, y_int, limit)
            source = "binance"
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
