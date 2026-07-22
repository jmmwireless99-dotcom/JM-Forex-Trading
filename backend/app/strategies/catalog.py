"""Structured strategy catalog for desk UI and API."""

from __future__ import annotations

from app.db.seed import SEED_STRATEGIES

_MANUAL_CARD = {
    "id": "manual_only",
    "name": "Manual desk",
    "sessions": ["Any time"],
    "session_slots": [],
    "timeframe": "M1 / M5",
    "signal_tf": "—",
    "chart_tf": "M1",
    "summary": "Manual BUY/SELL with auto SL/TP always available.",
    "entry_rules": [
        "Use desk Buy/Sell buttons — engine attaches default SL/TP on fill.",
        "Override stops with custom price or pip distance before submit.",
        "Works alongside any active auto strategy or with engine on manual_only.",
    ],
    "entry_flow": [
        "Pick side (BUY / SELL) and lot size.",
        "Optional: set SL/TP price or pips; auto_stops uses desk defaults.",
        "Position appears in open trades with unrealized P&L.",
    ],
    "parameters": {
        "auto_stops": True,
        "default_symbol": "XAUUSD",
    },
    "safety": [
        "Respects max open positions and daily loss limits.",
        "Manual path does not apply news/session strategy filters.",
    ],
    "order_type": "MARKET",
    "reward_r": None,
}


def _seed_params(name: str) -> dict:
    for spec in SEED_STRATEGIES:
        if spec["name"] == name:
            return dict(spec.get("parameters") or {})
    return {}


def strategy_catalog() -> list[dict]:
    """Return rich per-strategy cards for the scalp desk panel."""
    return [
        {
            "id": "London_Judas_Sweep",
            "name": "London Judas Sweep",
            "sessions": ["London"],
            "session_slots": ["london"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "London Judas Swing: Asian range trap → liquidity sweep → "
                "ChoCH → FVG 50% limit entry."
            ),
            "entry_rules": [
                "Build Asian box 00:00–06:00 UTC (high / low / mid).",
                "Active London strategy window 07:00–10:59 UTC (ends 11:00; wind-down then kill).",
                "Sweep: wick beyond Asia H/L by 50–350 pips ($0.50–$3.50), then reject inside.",
                "Remember the sweep — ChoCH/displacement + FVG can form on later M5 bars.",
                "Require ChoCH or displacement back through Asia mid after the sweep.",
                "Place LIMIT at bearish/bullish FVG 50% equilibrium (mid).",
                "Cancel pending limits at 12:00 UTC (kill switch).",
            ],
            "entry_flow": [
                "Sweep Asia H/L (remembered) → later ChoCH/displacement → FVG 50% LIMIT.",
                "SELL after Asia high sweep; BUY after Asia low sweep.",
                "SL beyond sweep wick + 80 pip ($0.80) buffer; TP Asia opposite side or 3R.",
            ],
            "parameters": _seed_params("London_Judas_Sweep"),
            "safety": [
                "Block if spread > 40 pips ($0.40 on XAUUSD).",
                "UK/EUR high-impact news blackout −15 minutes.",
                "Only fires once per session per FVG level.",
            ],
            "order_type": "LIMIT",
            "reward_r": 3.0,
        },
        {
            "id": "EMA_RSI_Scalp",
            "name": "EMA + RSI Scalp",
            "sessions": ["Asia", "New York"],
            "session_slots": ["asia", "new_york"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "EMA 200 trend filter + EMA 20/50 pullback zone + RSI 14 + "
                "engulfing or pin bar confirmation."
            ),
            "entry_rules": [
                "Uptrend: price above EMA200 and EMA20 ≥ EMA50.",
                "Downtrend: price below EMA200 and EMA20 ≤ EMA50.",
                "Wait for retest of EMA20/50 dynamic zone (or touch EMA20).",
                "RSI 35–55 for BUY; RSI 45–65 for SELL.",
                "Confirm with engulfing, pin bar, or soft directional M5 close.",
            ],
            "entry_flow": [
                "Trend aligned with EMA200 → pullback into EMA20/50 band.",
                "RSI in buy/sell zone + pattern → MARKET entry on bar close.",
                "SL/TP from ATR structure (≈1R stop, target max(1.6R, 1.8×ATR)).",
            ],
            "parameters": _seed_params("EMA_RSI_Scalp"),
            "safety": [
                "Auto router gates Asia/NY sessions; optional JM_SESSION_FILTER for avoid tiers.",
                "News blackout when desk news filter is on.",
                "Needs 205+ M5 bars for EMA200 warmup.",
            ],
            "order_type": "MARKET",
            "reward_r": 1.6,
        },
        {
            "id": "Liquidity_Sweep_SMC",
            "name": "Liquidity Sweep SMC",
            "sessions": ["London/NY overlap"],
            "session_slots": ["london_ny_overlap"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Smart Money Concepts: sweep Asia H/L or PDH/PDL → "
                "MSS/ChoCH → FVG or Order Block retest."
            ),
            "entry_rules": [
                "Mark liquidity: Asian High/Low (00:00–07:00 UTC) + PDH/PDL.",
                "Sweep: wick beyond level then close back inside (liquidity grab).",
                "Structure shift: MSS preferred after the sweep (recent swing break).",
                "Entry on retest of FVG or Order Block aligned with bias.",
                "Soft entry: directional candle after sweep if no zone touch yet.",
            ],
            "entry_flow": [
                "Detect sweep of ASIAN_HIGH/PDH (SELL) or ASIAN_LOW/PDL (BUY).",
                "Prefer MSS confirmation on last 20 M5 bars.",
                "Enter on FVG/OB retest or momentum candle → MARKET.",
            ],
            "parameters": _seed_params("Liquidity_Sweep_SMC"),
            "safety": [
                "Requires liquidity sweep before entry (require_sweep=True) — no MSS-only bypass.",
                "Session filter + news blackout when enabled.",
                "Needs 40+ M5 bars for zone/structure context.",
            ],
            "order_type": "MARKET",
            "reward_r": 1.8,
        },
        _MANUAL_CARD,
    ]


def entry_rules_short() -> list[str]:
    """One-line summaries kept for backward compatibility."""
    return [
        "London_Judas_Sweep — Asia box · $0.50–$3.50 sweep · later FVG50 LIMIT · kill 12:00",
        "EMA_RSI_Scalp — EMA200 trend · EMA20/50 retest · RSI 35-55/45-65 · engulf/pin/soft",
        "Liquidity_Sweep_SMC — Asia/PDH-PDL sweep · MSS/ChoCH · FVG/OB retest",
        "Manual BUY/SELL with auto SL/TP always available",
    ]
