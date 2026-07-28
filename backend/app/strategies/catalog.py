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
            "sessions": ["Manual only — paused from auto (paper lab)"],
            "session_slots": [],
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
                "Asia (UTC 00–07 / PH 8AM–3PM) — auto",
                "London (UTC 07–11 / PH 3–7PM) — auto paper lab",
            ],
            "session_slots": [
                "asia",
                "london",
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
            "sessions": [
                "London kill zone (UTC 07–11 / PH 3–7PM) when selected",
                "London/NY overlap (UTC 13–16 / PH 9PM–12AM) — auto prime",
            ],
            "session_slots": ["london_ny_overlap"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "SMC blueprint: PDH/PDL (priority) sweep → displacement + MSS/ChoCH → "
                "FVG50 LIMIT · SL beyond sweep wick · TP opposite liquidity / ≥2.8R."
            ),
            "entry_rules": [
                "Kill zones only: London UTC 07–11 + NY overlap UTC 13–16 (no dead hours).",
                "Mark PDH/PDL first, then Asia H/L + swings.",
                "Sweep: wick beyond level, close back inside (depth 0.35–2.8 ATR).",
                "Confirm: displacement candle + MSS/ChoCH after the sweep.",
                "LIMIT at FVG 50% equilibrium (MARKET if already through).",
                "SL beyond sweep wick (≥$1.50 / ATR buffer) · TP opposite major H/L or ≥2.8R.",
                "Skip if R:R < 2.0 · sweep expires after 18 M5 bars.",
            ],
            "entry_flow": [
                "PDH/PDL (or Asia/swing) sweep → displacement → MSS → FVG50 LIMIT.",
                "SELL after high sweep; BUY after low sweep.",
                "MT: fill near FVG mid (~120 pips) as market when limit is close.",
            ],
            "parameters": seed_params("Liquidity_Sweep_SMC"),
            "safety": [
                "Requires sweep + displacement + MSS (no bare structure entries).",
                "FVG50 LIMIT expires in 2 hours if unfilled.",
                "Session filter + news blackout when enabled.",
                "Needs 40+ M5 bars for zone/structure context.",
            ],
            "order_type": "LIMIT",
            "reward_r": 2.8,
        },
        {
            "id": "Trend_Breakout_ATR",
            "name": "Trend Breakout ATR",
            "sessions": [
                "New York (UTC 16–20 / PH 12–4AM) — auto",
                "London (UTC 07–11) when selected manually",
            ],
            "session_slots": ["new_york"],
            "timeframe": "M5",
            "signal_tf": "M5",
            "chart_tf": "M1",
            "summary": (
                "True trend/breakout + hard SL/TP: Donchian20 close-break · EMA200 "
                "filter · ADX · ATR buffer · ≈2.5R. No grid / no martingale."
            ),
            "entry_rules": [
                "Build Donchian 20-bar high/low (prior bars only).",
                "BUY: M5 close breaks above channel + ATR buffer · price > EMA200.",
                "SELL: M5 close breaks below channel + ATR buffer · price < EMA200.",
                "ADX ≥ 18 (skip chop) · channel width ≥ 0.8 ATR.",
                "MARKET entry · SL beyond opposite channel · TP ≥2.5R.",
                "Expect win rate ~45–60% — edge from R:R, not high win%.",
            ],
            "entry_flow": [
                "Range compress → directional close-break with trend filter.",
                "Hard SL/TP every trade · space breakouts ≥10 M5 bars.",
            ],
            "parameters": seed_params("Trend_Breakout_ATR"),
            "safety": [
                "No averaging / grid / martingale.",
                "Skip if R:R < 2.0 or ADX weak.",
                "News blackout + session avoid when filters on.",
            ],
            "order_type": "MARKET",
            "reward_r": 2.5,
        },
        _MANUAL_CARD,
    ]


def entry_rules_short() -> list[str]:
    """One-line summaries kept for backward compatibility."""
    return [
        "London_Judas_Sweep — Asia 00-06 · $0.80–$3.00 sweep · FVG50 LIMIT · kill 12:00",
        "EMA_RSI_Scalp — EMA200 · clear EMA20/50 · RSI · engulf/pin · SL@EMA50 · 2.5R",
        "Liquidity_Sweep_SMC — PDH/PDL sweep → displacement+MSS → FVG50 LIMIT · ≥2.8R",
        "Trend_Breakout_ATR — Donchian20 break · EMA200+ADX · hard SL · ≈2.5R · NY auto",
        "Manual BUY/SELL with auto SL/TP always available",
    ]
