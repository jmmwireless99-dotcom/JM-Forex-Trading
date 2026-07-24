"""Structured strategy catalog for desk UI and API."""

from __future__ import annotations

from app.db.seed import seed_params

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


def strategy_catalog() -> list[dict]:
    """Return rich per-strategy cards for the scalp desk panel."""
    return [
        {
            "id": "London_Judas_Sweep",
            "name": "London Judas Sweep",
            "sessions": ["London (UTC 07–11 / PH 3–7PM)"],
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
                "Prefer sweep 07:00–09:00 UTC; entry still allowed until 11:00.",
                "Sweep: wick beyond Asia H/L by 50–350 pips ($0.50–$3.50), then reject inside.",
                "Remember the sweep — ChoCH/displacement + FVG can form on later M5 bars.",
                "Require ChoCH or displacement back through Asia mid after the sweep.",
                "Place LIMIT at bearish/bullish FVG 50% equilibrium (mid).",
                "Cancel pending paper limits at 12:00 UTC (kill switch).",
                "MT4/MT5: fill as market only when price is near FVG mid (~150 pips).",
            ],
            "entry_flow": [
                "Sweep Asia H/L (remembered) → later ChoCH/displacement → FVG 50% LIMIT.",
                "SELL after Asia high sweep; BUY after Asia low sweep.",
                "SL beyond sweep wick + 80 pip ($0.80) buffer; TP Asia opposite side or 3R.",
            ],
            "parameters": seed_params("London_Judas_Sweep"),
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
            "sessions": [
                "Asia (UTC 00–07 / PH 8AM–3PM)",
                "London wind-down / close (UTC 11–13)",
                "New York (UTC 16–20 / PH 12–4AM)",
                "Off-hours (UTC 20–24)",
            ],
            "session_slots": [
                "asia",
                "london_wind_down",
                "london_close",
                "new_york",
                "off_hours",
            ],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "EMA 200 trend filter + EMA 20/50 pullback zone + RSI 14 + "
                "engulfing / pin / strong-body confirmation."
            ),
            "entry_rules": [
                "Uptrend: price above EMA200 and EMA20 ≥ EMA50.",
                "Downtrend: price below EMA200 and EMA20 ≤ EMA50.",
                "Wait for retest of EMA20/50 dynamic zone (or touch EMA20).",
                "RSI 38–52 for BUY; RSI 48–62 for SELL.",
                "Confirm with engulfing, pin bar, or strong directional M5 body.",
                "Cooldown spacing ≥6 M5 bars; no auto reverse — holds to SL/TP.",
            ],
            "entry_flow": [
                "Trend aligned with EMA200 → pullback into EMA20/50 band.",
                "RSI in buy/sell zone + pattern → MARKET entry on bar close.",
                "SL/TP from ATR structure (wider stops: ~1.4×ATR / ~2.2×ATR).",
            ],
            "parameters": seed_params("EMA_RSI_Scalp"),
            "safety": [
                "Auto router gates Asia/NY sessions; optional JM_SESSION_FILTER for avoid tiers.",
                "News blackout when desk news filter is on.",
                "Needs 205+ M5 bars for EMA200 warmup.",
                "Daily loss kill-switch disabled by default (JM_MAX_DAILY_LOSS_PCT=0).",
            ],
            "order_type": "MARKET",
            "reward_r": 1.8,
        },
        {
            "id": "Liquidity_Sweep_SMC",
            "name": "Liquidity Sweep SMC",
            "sessions": ["London/NY overlap (UTC 13–16 / PH 9PM–12AM)"],
            "session_slots": ["london_ny_overlap"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Smart Money Concepts: sweep Asia H/L (00–06), PDH/PDL, or recent "
                "swing → MSS → FVG or Order Block retest."
            ),
            "entry_rules": [
                "Mark liquidity: Asian High/Low (00:00–06:00 UTC) + PDH/PDL + recent swings.",
                "Sweep: wick beyond level then close back inside (liquidity grab).",
                "Structure shift: MSS preferred after the sweep (recent swing break).",
                "Entry only on retest of real FVG or Order Block aligned with bias.",
                "No synthetic momentum OB — wait for zone touch.",
            ],
            "entry_flow": [
                "Detect sweep of ASIAN_HIGH/PDH/SWING_HIGH (SELL) or LOW side (BUY).",
                "Prefer MSS confirmation on last 20 M5 bars.",
                "Enter on FVG/OB retest → MARKET.",
            ],
            "parameters": seed_params("Liquidity_Sweep_SMC"),
            "safety": [
                "Requires liquidity sweep before entry (require_sweep=True).",
                "Requires FVG/OB retest (require_zone_retest=True).",
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
        "London_Judas_Sweep — Asia 00-06 · $0.50–$3.50 sweep · FVG50 LIMIT · kill 12:00",
        "EMA_RSI_Scalp — EMA200 · EMA20/50 retest · RSI 38-52/48-62 · strong body/pin · hold SL/TP",
        "Liquidity_Sweep_SMC — Asia/PDH/swing sweep · MSS · FVG/OB retest only",
        "Manual BUY/SELL with auto SL/TP always available",
    ]
