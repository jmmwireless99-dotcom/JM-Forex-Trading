from __future__ import annotations

from typing import Any

# Strategy ids used by auto engine
STRATEGIES: dict[str, dict[str, Any]] = {
    "EMA_RSI_SCALP": {
        "name": "EMA+RSI Scalper",
        "description": "M5 EMA 20/50 + RSI 14 — trend + candle confirm for EUR/USD.",
        "pairs": ["EURUSD"],
    },
    "BREAKOUT": {
        "name": "Range Breakout",
        "description": "M5 close breaks 24-bar range with buffer — GBP/USD.",
        "pairs": ["GBPUSD"],
    },
    "MEAN_REVERT": {
        "name": "Mean Reversion (grid-lite)",
        "description": "Fade range edges with trend + rejection filter — no martingale.",
        "pairs": ["AUDNZD", "EURCHF"],
    },
    "EMA_RSI_TREND": {
        "name": "EMA+RSI Trend",
        "description": "M5 EMA 20/50 + RSI — wider SL and spacing for XAUUSD volatility.",
        "pairs": ["XAUUSD"],
    },
}

# Default auto settings per pair when user starts auto
PAIR_PRESETS: dict[str, dict[str, Any]] = {
    "EURUSD": {
        "strategy": "EMA_RSI_SCALP",
        "lots": 0.01,
        "sl_pips": 14.0,
        "tp_pips": 28.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 3,
        "label": "Scalper · EMA+RSI",
    },
    "GBPUSD": {
        "strategy": "BREAKOUT",
        "lots": 0.01,
        "sl_pips": 20.0,
        "tp_pips": 40.0,
        "min_bars_between": 2,
        "cooldown_bars_after_loss": 4,
        "label": "Breakout · 24-bar range",
    },
    "AUDNZD": {
        "strategy": "MEAN_REVERT",
        "lots": 0.01,
        "sl_pips": 16.0,
        "tp_pips": 32.0,
        "min_bars_between": 3,
        "cooldown_bars_after_loss": 4,
        "label": "Mean revert · range edges",
    },
    "EURCHF": {
        "strategy": "MEAN_REVERT",
        "lots": 0.01,
        "sl_pips": 14.0,
        "tp_pips": 28.0,
        "min_bars_between": 4,
        "cooldown_bars_after_loss": 6,
        "label": "Mean revert · filtered",
    },
    "XAUUSD": {
        "strategy": "EMA_RSI_TREND",
        "lots": 0.01,
        "sl_pips": 70.0,
        "tp_pips": 120.0,
        "min_bars_between": 4,
        "cooldown_bars_after_loss": 5,
        "label": "Trend · EMA+RSI gold",
    },
}


def preset_for(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    return dict(PAIR_PRESETS.get(sym, PAIR_PRESETS["EURUSD"]))


def strategy_info(strategy_id: str) -> dict[str, Any]:
    return STRATEGIES.get(strategy_id, STRATEGIES["EMA_RSI_SCALP"])
