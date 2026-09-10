"""Fetch live gold OHLC for dashboard display.

Primary: Yahoo GC=F (COMEX futures)
Fallback: Binance PAXGUSDT (Paxos Gold — tracks spot closely)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_CHART_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_SYMBOL = "GC=F"
BINANCE_SYMBOL = "PAXGUSDT"

INTERVAL_MAP = {
    "1": "5m",  # Yahoo 1m often restricted; use 5m floor for display
    "1m": "5m",
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

BINANCE_INTERVAL = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "1h",
    "1h": "1h",
    "1d": "1d",
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 20.0


def _yahoo_range_for_interval(interval: str) -> str:
    if interval in {"1m", "5m", "15m"}:
        return "5d"
    if interval in {"30m", "60m", "1h"}:
        return "1mo"
    if interval in {"1d", "1wk"}:
        return "1mo"
    return "3mo"


def _http_json(url: str, timeout: float = 12) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _from_yahoo(symbol: str, y_interval: str, limit: int) -> dict[str, Any]:
    y_range = _yahoo_range_for_interval(y_interval)
    params = urllib.parse.urlencode({"interval": y_interval, "range": y_range})
    urls = [
        f"{YAHOO_CHART.format(symbol=urllib.parse.quote(symbol))}?{params}",
        f"{YAHOO_CHART_ALT.format(symbol=urllib.parse.quote(symbol))}?{params}",
    ]
    payload = None
    last_err: Exception | None = None
    for url in urls:
        try:
            payload = _http_json(url)
            break
        except Exception as e:
            last_err = e
            logger.warning("yahoo gold attempt failed: %s", e)
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
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
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
    return {
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


def _parse_binance_rows(rows: list) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for row in rows:
        # [open_time, open, high, low, close, volume, close_time, ...]
        ts = int(row[0]) // 1000
        candles.append(
            {
                "time": ts,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "open_time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            }
        )
    return candles


def _from_binance(y_interval: str, limit: int) -> dict[str, Any]:
    b_interval = BINANCE_INTERVAL.get(y_interval, "5m")
    want = min(max(limit, 50), 9000)
    candles: list[dict[str, Any]] = []
    end_ms: int | None = None
    while len(candles) < want:
        batch = min(1000, want - len(candles))
        params: dict[str, str | int] = {
            "symbol": BINANCE_SYMBOL,
            "interval": b_interval,
            "limit": batch,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        rows = _http_json(f"{BINANCE_KLINES}?{urllib.parse.urlencode(params)}")
        if not isinstance(rows, list) or not rows:
            break
        batch_candles = _parse_binance_rows(rows)
        if end_ms is None:
            candles = batch_candles
        else:
            candles = batch_candles + candles
        if len(rows) < batch:
            break
        end_ms = int(rows[0][0]) - 1
    if not candles:
        raise RuntimeError("Binance PAXG returned no klines")
    last = candles[-1]
    return {
        "ok": True,
        "source": "binance",
        "symbol": BINANCE_SYMBOL,
        "label": "Pax Gold (PAXGUSDT) · live market proxy",
        "interval": b_interval,
        "price": last["close"],
        "currency": "USDT",
        "exchange": "Binance",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "candles": candles,
    }


def _m5_bars_for_days(days: int) -> int:
    """Approximate closed 5m bars for N calendar days."""
    return min(max(int(days) * 288, 50), 9000)


def fetch_gold_candles(
    *,
    interval: str = "5m",
    symbol: str = DEFAULT_SYMBOL,
    limit: int = 300,
    days: int | None = None,
) -> dict[str, Any]:
    y_interval = INTERVAL_MAP.get(str(interval), "5m")
    if days is not None and y_interval == "5m":
        limit = max(limit, _m5_bars_for_days(days))
    cache_key = f"{symbol}:{y_interval}:{limit}:{days or 0}"
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit and now - hit[0] < _CACHE_TTL_SEC:
        return hit[1]

    errors: list[str] = []
    out: dict[str, Any] | None = None
    # Yahoo caps 5m at ~5 days — use Binance pagination for longer M5 history.
    use_binance_first = y_interval == "5m" and (days or 0) > 5
    if not use_binance_first:
        try:
            out = _from_yahoo(symbol, y_interval, limit)
        except Exception as e:
            errors.append(f"yahoo: {e}")
            logger.warning("yahoo gold feed failed, trying Binance PAXG: %s", e)

    if out is None or not out.get("candles"):
        try:
            out = _from_binance(y_interval, limit)
        except Exception as e:
            errors.append(f"binance: {e}")
            raise RuntimeError("Gold market feed unavailable: " + " | ".join(errors)) from e

    if days is not None and out.get("candles"):
        cutoff = int(now) - int(days) * 86400
        out["candles"] = [c for c in out["candles"] if c["time"] >= cutoff]

    _CACHE[cache_key] = (now, out)
    return out
