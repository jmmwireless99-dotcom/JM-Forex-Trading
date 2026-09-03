from __future__ import annotations

from typing import Any

# Strategy ids used by auto engine
STRATEGIES: dict[str, dict[str, Any]] = {
    "EMA_RSI_SCALP": {
        "name": "EMA+RSI Scalper",
        "description": "M5 EMA 20/50 + RSI 14 — tight zones for EUR/USD scalping.",
        "pairs": ["EURUSD"],
    },
    "BREAKOUT": {
        "name": "Range Breakout",
        "description": "M5 close breaks 24-bar high/low — trend/breakout style for GBP/USD.",
        "pairs": ["GBPUSD"],
    },
    "MEAN_REVERT": {
        "name": "Mean Reversion (grid-lite)",
        "description": "Buy range bottom / sell range top — ranging pairs (no martingale).",
        "pairs": ["AUDNZD", "EURCHF"],
    },
    "EMA_RSI_TREND": {
        "name": "EMA+RSI Trend",
        "description": "M5 EMA 20/50 + RSI 14 — wider zones for volatile XAUUSD.",
        "pairs": ["XAUUSD"],
    },
}

# Default auto settings per pair when user starts auto (lots fixed at 0.03)
PAIR_PRESETS: dict[str, dict[str, Any]] = {
    "EURUSD": {
        "strategy": "EMA_RSI_SCALP",
        "lots": 0.03,
        "sl_pips": 12.0,
        "tp_pips": 24.0,
        "label": "Scalper · EMA+RSI",
    },
    "AUDNZD": {
        "strategy": "MEAN_REVERT",
        "lots": 0.03,
        "sl_pips": 14.0,
        "tp_pips": 20.0,
        "label": "Mean revert · range edges",
    },
    "EURCHF": {
        "strategy": "MEAN_REVERT",
        "lots": 0.03,
        "sl_pips": 10.0,
        "tp_pips": 16.0,
        "label": "Mean revert · Asian range",
    },
    "XAUUSD": {
        "strategy": "EMA_RSI_TREND",
        "lots": 0.03,
        "sl_pips": 20.0,
        "tp_pips": 40.0,
        "label": "Trend · EMA+RSI gold",
    },
}


def preset_for(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    return dict(PAIR_PRESETS.get(sym, PAIR_PRESETS["EURUSD"]))


def strategy_info(strategy_id: str) -> dict[str, Any]:
    return STRATEGIES.get(strategy_id, STRATEGIES["EMA_RSI_SCALP"])
