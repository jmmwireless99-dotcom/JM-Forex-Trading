"""Claude reads TradingView-style gold chart data (OHLC + desk context)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


@dataclass
class ClaudeAnalysis:
    ok: bool
    bias: str = "NEUTRAL"  # BUY | SELL | NEUTRAL | WAIT
    summary: str = ""
    structure: str = ""
    levels: dict[str, float | None] | None = None
    risk_notes: list[str] | None = None
    confluence: list[str] | None = None
    raw: str = ""
    model: str = ""
    source: str = "claude"
    chart: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 2)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def summarize_candles(candles: list[dict[str, Any]], *, tail: int = 60) -> dict[str, Any]:
    rows = sorted(candles, key=lambda c: int(c.get("time") or 0))
    if not rows:
        return {}
    closes = [float(c["close"]) for c in rows if c.get("close") is not None]
    highs = [float(c["high"]) for c in rows if c.get("high") is not None]
    lows = [float(c["low"]) for c in rows if c.get("low") is not None]
    if not closes:
        return {}
    last = rows[-1]
    window = rows[-tail:]
    return {
        "bars_total": len(rows),
        "bars_sent": len(window),
        "interval_note": "TradingView-style gold OHLC (GC=F / PAXG proxy)",
        "last_time": datetime.fromtimestamp(int(last["time"]), tz=timezone.utc).isoformat(),
        "last_ohlc": {
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
        },
        "range_high": round(max(highs[-tail:]), 2),
        "range_low": round(min(lows[-tail:]), 2),
        "change_pct": round((closes[-1] - closes[0]) / closes[0] * 100, 2) if len(closes) > 1 else 0,
        "ema20": _ema(closes, 20),
        "ema50": _ema(closes, 50),
        "ema200": _ema(closes, 200),
        "rsi14": _rsi(closes, 14),
        "recent_bars": [
            {
                "t": datetime.fromtimestamp(int(c["time"]), tz=timezone.utc).strftime("%m-%d %H:%M"),
                "o": round(float(c["open"]), 2),
                "h": round(float(c["high"]), 2),
                "l": round(float(c["low"]), 2),
                "c": round(float(c["close"]), 2),
            }
            for c in window[-40:]
        ],
    }


def _build_prompt(
    *,
    chart: dict[str, Any],
    desk: dict[str, Any] | None,
    signals: list[dict[str, Any]] | None,
    tv_alert: dict[str, Any] | None,
    symbol: str,
    timeframe: str,
) -> str:
    parts = [
        "You are Claude, the chart analyst for JM FX gold desk (XAUUSD / TVC:GOLD).",
        "Read the TradingView-style OHLC snapshot and desk context. Reply in JSON only.",
        "",
        f"Symbol: {symbol} · Timeframe: {timeframe}",
        "",
        "CHART_SNAPSHOT:",
        json.dumps(chart, indent=2),
    ]
    if desk:
        parts += ["", "DESK_CONTEXT:", json.dumps(desk, indent=2)]
    if signals:
        parts += ["", "RECENT_SIGNALS:", json.dumps(signals[:8], indent=2)]
    if tv_alert:
        parts += ["", "TRADINGVIEW_ALERT:", json.dumps(tv_alert, indent=2)]
    parts += [
        "",
        "Return strict JSON:",
        "{",
        '  "bias": "BUY|SELL|NEUTRAL|WAIT",',
        '  "summary": "2-3 sentences in plain English/Taglish OK",',
        '  "structure": "trend, sweep, range, key pattern",',
        '  "levels": {"support": number|null, "resistance": number|null, "invalidation": number|null},',
        '  "confluence": ["bullet", "..."],',
        '  "risk_notes": ["bullet", "..."]',
        "}",
        "Be concise. Use the OHLC numbers given — do not invent prices far from last close.",
    ]
    return "\n".join(parts)


def _parse_claude_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


class ClaudeChartAnalyst:
    """Calls Anthropic Messages API to interpret chart + TradingView alerts."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        enabled: bool = True,
        timeout: float = 45.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = model or DEFAULT_MODEL
        self.enabled = enabled and bool(self.api_key)
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.api_key),
            "enabled": self.enabled,
            "model": self.model,
            "provider": "anthropic",
        }

    async def analyze_chart(
        self,
        *,
        candles: list[dict[str, Any]],
        symbol: str = "XAUUSD",
        timeframe: str = "M5",
        desk: dict[str, Any] | None = None,
        signals: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ClaudeAnalysis:
        if not self.enabled:
            return ClaudeAnalysis(
                ok=False,
                error="Claude not configured — set JM_ANTHROPIC_API_KEY",
            )
        chart = summarize_candles(candles)
        if meta:
            chart["feed"] = {
                "source": meta.get("source"),
                "label": meta.get("label"),
                "price": meta.get("price"),
            }
        desk_ctx = _compact_desk(desk) if desk else None
        prompt = _build_prompt(
            chart=chart,
            desk=desk_ctx,
            signals=signals,
            tv_alert=None,
            symbol=symbol,
            timeframe=timeframe,
        )
        return await self._call(prompt, chart=chart)

    async def analyze_tradingview_alert(
        self,
        alert: dict[str, Any],
        *,
        candles: list[dict[str, Any]] | None = None,
        desk: dict[str, Any] | None = None,
    ) -> ClaudeAnalysis:
        if not self.enabled:
            return ClaudeAnalysis(
                ok=False,
                error="Claude not configured — set JM_ANTHROPIC_API_KEY",
            )
        chart = summarize_candles(candles or []) if candles else {}
        prompt = _build_prompt(
            chart=chart or {"note": "no candle history — alert only"},
            desk=_compact_desk(desk) if desk else None,
            signals=None,
            tv_alert=alert,
            symbol=str(alert.get("symbol") or alert.get("ticker") or "XAUUSD"),
            timeframe=str(alert.get("interval") or alert.get("timeframe") or "M5"),
        )
        return await self._call(prompt, chart=chart or None)

    async def _call(self, prompt: str, *, chart: dict[str, Any] | None) -> ClaudeAnalysis:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 900,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(ANTHROPIC_URL, headers=headers, json=body)
            if resp.status_code >= 400:
                detail = resp.text[:400]
                logger.warning("claude api error %s: %s", resp.status_code, detail)
                return ClaudeAnalysis(ok=False, error=f"Claude API {resp.status_code}: {detail}")
            payload = resp.json()
            blocks = payload.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            parsed = _parse_claude_json(text)
            return ClaudeAnalysis(
                ok=True,
                bias=str(parsed.get("bias") or "NEUTRAL").upper(),
                summary=str(parsed.get("summary") or ""),
                structure=str(parsed.get("structure") or ""),
                levels=parsed.get("levels") if isinstance(parsed.get("levels"), dict) else {},
                risk_notes=list(parsed.get("risk_notes") or []),
                confluence=list(parsed.get("confluence") or []),
                raw=text,
                model=self.model,
                chart=chart,
            )
        except json.JSONDecodeError as e:
            return ClaudeAnalysis(ok=False, error=f"Claude JSON parse failed: {e}", raw=text if "text" in locals() else "")
        except Exception as e:  # noqa: BLE001
            logger.exception("claude analyze failed")
            return ClaudeAnalysis(ok=False, error=str(e))


def _compact_desk(desk: dict[str, Any]) -> dict[str, Any]:
    return {
        "session": desk.get("session"),
        "signal_timeframe": desk.get("signal_timeframe"),
        "active_strategy": desk.get("active_strategy"),
        "auto": {
            "allow_trading": (desk.get("auto") or {}).get("decision", {}).get("allow_trading"),
            "reason": (desk.get("auto") or {}).get("decision", {}).get("reason"),
            "regime": (desk.get("auto") or {}).get("decision", {}).get("regime"),
        },
        "asia_range": desk.get("asia_range"),
        "last_block_reason": desk.get("last_block_reason"),
        "entry_checklist": (desk.get("entry_checklist") or [])[:6],
        "news_blocked": (desk.get("news") or {}).get("blocked"),
    }
