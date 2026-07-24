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
                "New York (UTC 16–20 / PH 12–4AM; Fri cuts at 18:00 UTC)",
            ],
            "session_slots": [
                "asia",
                "new_york",
            ],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Best EMA pullback: EMA200 + clear EMA20/50 stack + RSI + "
                "engulf/pin · SL beyond EMA50 · TP ≈2.5R."
            ),
            "entry_rules": [
                "Uptrend: price above EMA200, EMA20 ≥ EMA50, clear EMA separation.",
                "Downtrend: price below EMA200, EMA20 ≤ EMA50, clear EMA separation.",
                "Wait for retest of EMA20/50 dynamic zone (or touch EMA20).",
                "RSI 40–50 for BUY; RSI 50–60 for SELL.",
                "Confirm with engulfing or pin bar only.",
                "BUY or SELL whenever confluence is complete — no daily trade cap.",
            ],
            "entry_flow": [
                "Trend aligned with EMA200 → pullback into EMA20/50 band.",
                "RSI in buy/sell zone + pattern → MARKET entry on bar close.",
                "SL beyond EMA50/structure (capped) · TP ≥2.5R / ~3×ATR.",
            ],
            "parameters": seed_params("EMA_RSI_Scalp"),
            "safety": [
                "Auto router gates Asia/NY quality windows; stand aside off-hours + Fri late.",
                "News blackout when desk news filter is on.",
                "Needs 205+ M5 bars for EMA200 warmup.",
                "Daily loss kill-switch disabled by default (JM_MAX_DAILY_LOSS_PCT=0).",
            ],
            "order_type": "MARKET",
            "reward_r": 2.5,
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
                "Best SMC: sweep Asia H/L / PDH-PDL / swing → MSS → FVG/OB retest · "
                "SL beyond sweep · unlimited quality BUY/SELL."
            ),
            "entry_rules": [
                "Mark liquidity: Asian High/Low (00:00–06:00 UTC) + PDH/PDL + recent swings.",
                "Sweep: wick beyond level then close back inside (liquidity grab).",
                "Structure shift: MSS must confirm the sweep bias.",
                "Entry on FVG (preferred) or Order Block retest aligned with bias.",
                "No daily trade limit — every complete setup may fire (BUY or SELL).",
            ],
            "entry_flow": [
                "Detect sweep of ASIAN_HIGH/PDH/SWING_HIGH (SELL) or LOW side (BUY).",
                "Require MSS confirmation on last 20 M5 bars.",
                "Enter on FVG/OB retest → MARKET · SL beyond sweep extreme · TP ≈2.5R.",
            ],
            "parameters": seed_params("Liquidity_Sweep_SMC"),
            "safety": [
                "Requires liquidity sweep before entry (require_sweep=True).",
                "Requires FVG/OB retest (require_zone_retest=True).",
                "Session filter + news blackout when enabled.",
                "Needs 40+ M5 bars for zone/structure context.",
            ],
            "order_type": "MARKET",
            "reward_r": 2.5,
        },
        {
            "id": "BTC_EMA_RSI_Scalp",
            "name": "BTC EMA + RSI Scalp",
            "sessions": ["BTCUSD 24/7 (manual select — not gold auto-router)"],
            "session_slots": [],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "Best BTCUSD desk strategy: EMA200 trend + EMA20/50 pullback + RSI + "
                "engulf/pin · structure SL · ≈2.2R · signal TF M5."
            ),
            "entry_rules": [
                "Symbol BTCUSD only — gold strategies stay on XAUUSD.",
                "TIMEFRAME: M5 signals (attach MT4 EA on BTCUSD M5).",
                "Uptrend: price > EMA200, EMA20 ≥ EMA50, clear separation.",
                "Pullback into EMA20/50 + RSI 38–52 BUY / 48–62 SELL.",
                "Confirm with engulfing or pin bar (no soft body).",
                "Manual Apply + Save preferred strategy on your account.",
            ],
            "entry_flow": [
                "Select BTC_EMA_RSI_Scalp → Apply strategy (manual) → Save.",
                "Engine locks this strategy (auto gold transfer OFF).",
                "Paper: Binance BTCUSDT mid · Live MT4: jm-mt4-btc-bridge.zip.",
            ],
            "parameters": seed_params("BTC_EMA_RSI_Scalp"),
            "safety": [
                "Not on gold session auto-router — must select manually.",
                "MT4 live: attach EA on BTCUSD M5 + RUN_AGENT_MT4_BTC.bat.",
                "Needs 205+ M5 BTC bars (seeded from Binance on boot).",
            ],
            "order_type": "MARKET",
            "reward_r": 2.2,
        },
        _MANUAL_CARD,
    ]


def entry_rules_short() -> list[str]:
    """One-line summaries kept for backward compatibility."""
    return [
        "London_Judas_Sweep — Asia 00-06 · $0.80–$3.00 sweep · FVG50 LIMIT · kill 12:00",
        "EMA_RSI_Scalp — EMA200 · clear EMA20/50 · RSI · engulf/pin · SL@EMA50 · 2.5R",
        "Liquidity_Sweep_SMC — sweep+MSS+FVG/OB · SL beyond sweep · unlimited quality",
        "BTC_EMA_RSI_Scalp — BTCUSD EMA200 pullback · RSI · engulf/pin · manual save",
        "Manual BUY/SELL with auto SL/TP always available",
    ]
