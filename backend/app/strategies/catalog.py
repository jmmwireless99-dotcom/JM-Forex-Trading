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
            "id": "AI_ML",
            "name": "AI & Machine Learning",
            "sessions": ["Asia", "London/NY overlap", "New York"],
            "session_slots": ["asia", "london_ny_overlap", "new_york"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Primary JM FX stack: session child setup + AI & Machine Learning "
                "win-probability filter (scikit-learn)."
            ),
            "entry_rules": [
                "Asia → EMA_RSI_Scalp child · London 07–11 stand aside · Overlap → SMC · NY → VWAP.",
                "Child must print a valid setup on M5 close.",
                "ML scores TAKE / CAUTION / SKIP from labeled trade history.",
                "SKIP is blocked inside AI_ML (no order sent).",
                "Model updates online on every closed trade; Retrain runs batch LogisticRegression.",
            ],
            "entry_flow": [
                "Session auto-follow parks AI_ML.",
                "Child strategy builds signal → ML filter → MARKET/LIMIT if TAKE/CAUTION.",
            ],
            "parameters": _seed_params("AI_ML"),
            "safety": [
                "Learns from your SL/TP history — weak Asia soft setups score low.",
                "Optional JM_AI_GATE_ENTRIES also blocks SKIP at the engine layer.",
                "Needs labeled closes to improve beyond cold-start coefficients.",
            ],
            "order_type": "MARKET",
            "reward_r": None,
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
                "RSI 38–52 for BUY; RSI 48–62 for SELL.",
                "Confirm with engulfing, pin bar, or soft directional M5 close.",
                "Cooldown spacing ≥6 M5 bars; no auto reverse — holds to SL/TP.",
            ],
            "entry_flow": [
                "Trend aligned with EMA200 → pullback into EMA20/50 band.",
                "RSI in buy/sell zone + pattern → MARKET entry on bar close.",
                "SL/TP from ATR structure (Asia scalp: ~1.15×ATR SL · 1:2 TP).",
            ],
            "parameters": _seed_params("EMA_RSI_Scalp"),
            "safety": [
                "Auto router gates Asia/NY sessions; optional JM_SESSION_FILTER for avoid tiers.",
                "News blackout when desk news filter is on.",
                "Needs 205+ M5 bars for EMA200 warmup.",
                "Daily loss kill-switch disabled by default (JM_MAX_DAILY_LOSS_PCT=0).",
            ],
            "order_type": "MARKET",
            "reward_r": 2.0,
        },
        {
            "id": "EMA_VWAP_Scalp",
            "name": "EMA + VWAP Scalp",
            "sessions": ["New York", "London/NY overlap"],
            "session_slots": ["new_york", "london_ny_overlap"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "9/21 EMA crossover with session VWAP filter — systematic "
                "long/short signals during peak liquidity."
            ),
            "entry_rules": [
                "Long: 9 EMA crosses above 21 EMA with price above session VWAP.",
                "Short: 9 EMA crosses below 21 EMA with price below session VWAP.",
                "Stop-loss at recent swing low/high (tight structure stop).",
                "Take-profit at 1:2 risk-reward; hold to SL/TP (no auto reverse).",
                "Cooldown ≥3 M5 bars between signals; flip blocked until setup matures.",
            ],
            "entry_flow": [
                "Wait for EMA 9/21 crossover on M5 bar close.",
                "Confirm price is on the correct side of session VWAP.",
                "MARKET entry with swing-based SL and 2R TP.",
            ],
            "parameters": _seed_params("EMA_VWAP_Scalp"),
            "safety": [
                "Best during peak XAUUSD liquidity (NY / overlap sessions).",
                "News blackout when desk news filter is on.",
                "Needs 26+ M5 bars for EMA21 warmup.",
            ],
            "order_type": "MARKET",
            "reward_r": 2.5,
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
                "immediate rejection, retest, FVG/OB, or momentum entry."
            ),
            "entry_rules": [
                "Mark liquidity: Asian High/Low (PH 7AM–8PM box) + PDH/PDL + swing pool.",
                "Sweep: wick beyond level with rejection (not a clean breakout).",
                "Enter on sweep bar, retest of swept level, FVG/OB, or soft momentum.",
                "Structure shift (MSS) preferred but not required when sweep is fresh.",
                "Up to 4 entries per day; sweep memory expires after 18 M5 bars (~90 min).",
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
            "reward_r": 2.5,
        },
        {
            "id": "NewsBreakout",
            "name": "News Breakout",
            "sessions": ["News days — NFP, CPI, FOMC, Core PCE"],
            "session_slots": ["news_day"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Auto-runs on high-impact USD news days instead of AI_ML. "
                "Post-spike break flags a setup; entry only on retest + "
                "rejection candle — pinakamaligtas na paraan, hindi habol-presyo."
            ),
            "entry_rules": [
                "Desk auto-switches from AI_ML on PH evening when T-60m before news.",
                "Arms 1 hour before NFP/CPI/FOMC/PCE — PH 7PM–7AM only.",
                "Wait +5 min after release — skip initial whipsaw.",
                "Strong M5 body breaking pre-release 6-bar range flags a pending setup.",
                "Entry fires only when price retests the broken level with a "
                "pin bar / engulfing rejection candle (within 6 M5 bars).",
                "Wide ATR stops (3× SL · 2R TP) — max 2 trades per news day.",
            ],
            "entry_flow": [
                "Router parks NewsBreakout T-60m → T+60m around release (PH evening).",
                "Inside post-release window → directional break → pending (no order yet).",
                "Retest of broken level + rejection candle within 6 bars → MARKET.",
                "Missed retest (6 bars, ~30m) → setup dropped, no chase entry.",
                "EMA_RSI / SMC unchanged on normal days.",
            ],
            "parameters": _seed_params("NewsBreakout"),
            "safety": [
                "Bypasses normal news blackout — designed for news volatility.",
                "ML gate skipped for NewsBreakout signals (separate from AI_ML).",
                "Normal strategies still block during news when news_filter=true.",
            ],
            "order_type": "MARKET",
            "reward_r": 2.0,
        },
        _MANUAL_CARD,
    ]


def entry_rules_short() -> list[str]:
    """One-line summaries kept for backward compatibility."""
    return [
        "AI_ML — session child (EMA_RSI) + AI & Machine Learning filter",
        "PH desk — 7AM–8PM EMA_RSI · 8PM–2AM SMC · 2AM–7AM EMA_RSI",
        "EMA_RSI_Scalp — EMA200 trend · EMA20/50 retest · RSI 38-52/48-62 · spaced entries · hold SL/TP",
        "EMA_VWAP_Scalp — EMA9/21 crossover · session VWAP filter · swing SL · 2R TP",
        "Liquidity_Sweep_SMC — Asia/PDH sweep · immediate/retest/FVG entry · 18-bar sweep memory",
        "NewsBreakout — PH gabi T-60m→T+60m around news · post-spike entry · wide ATR stops",
        "Manual BUY/SELL with auto SL/TP always available",
    ]
