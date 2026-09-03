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
        "name": "Gold EMA+RSI Scalper",
        "description": (
            "M5 EMA 20/50 + RSI 14 — wider zones for XAUUSD scalping "
            "(restored from strict EMA200/RSI8 review preset)."
        ),
        "pairs": ["XAUUSD"],
    },
}

# Default auto settings per pair when user starts auto
PAIR_PRESETS: dict[str, dict[str, Any]] = {
    "EURUSD": {
        "strategy": "EMA_RSI_SCALP",
        "lots": 0.03,
        "sl_pips": 14.0,
        "tp_pips": 28.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 3,
        "max_spread_pips": 2.0,
        "label": "Scalper · EMA+RSI",
    },
    "GBPUSD": {
        "strategy": "BREAKOUT",
        "lots": 0.03,
        "sl_pips": 18.0,
        "tp_pips": 36.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 3,
        "label": "Breakout · 24-bar range",
    },
    "AUDNZD": {
        "strategy": "MEAN_REVERT",
        "lots": 0.03,
        "sl_pips": 16.0,
        "tp_pips": 32.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 4,
        "label": "Mean revert · range edges",
    },
    "EURCHF": {
        "strategy": "MEAN_REVERT",
        "lots": 0.03,
        "sl_pips": 14.0,
        "tp_pips": 28.0,
        "min_bars_between": 4,
        "cooldown_bars_after_loss": 6,
        "label": "Mean revert · filtered",
    },
    "XAUUSD": {
        "strategy": "EMA_RSI_TREND",
        "lots": 0.03,
        "sl_pips": 20.0,
        "tp_pips": 40.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 4,
        "max_spread_pips": 3.5,
        "label": "Gold scalper · EMA+RSI",
    },
}


def preset_for(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    return dict(PAIR_PRESETS.get(sym, PAIR_PRESETS["EURUSD"]))


def strategy_info(strategy_id: str) -> dict[str, Any]:
    sid = (strategy_id or "EMA_RSI_SCALP").upper()
    # Legacy VPS ids → same gold scalper stack
    if sid in {"GOLD_EMA_RSI", "EMA_RSI_TREND"} and sid not in STRATEGIES:
        return STRATEGIES["EMA_RSI_TREND"]
    return STRATEGIES.get(sid, STRATEGIES["EMA_RSI_SCALP"])
