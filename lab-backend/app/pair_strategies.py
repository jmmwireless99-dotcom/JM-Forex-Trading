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
        "name": "Gold EMA+RSI (Review)",
        "description": (
            "M5 EMA 20/50/200 + RSI(8) · oversold 40 / overbought 60 · "
            "30p SL / 75p TP (1:2.5) · min 15p signal candle · 1% auto risk."
        ),
        "pairs": ["XAUUSD"],
    },
    "GOLD_EMA_RSI": {
        "name": "Gold EMA+RSI (Review)",
        "description": "Alias for EMA_RSI_TREND gold review preset.",
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
        "label": "Scalper · EMA+RSI",
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
        "sl_pips": 30.0,
        "tp_pips": 75.0,
        "min_bars_between": 4,
        "cooldown_bars_after_loss": 5,
        # Flat 0.03 lot per trade like the other 4 pairs — auto_risk sizing
        # (1% equity / SL distance) would otherwise override the flat lot.
        "auto_risk": False,
        "risk_pct": 1.0,
        "max_spread_pips": 3.5,
        "breakout_min_pips": 15.0,
        "ema_fast": 20,
        "ema_medium": 50,
        "ema_slow": 200,
        "rsi_period": 8,
        "rsi_oversold": 40.0,
        "rsi_overbought": 60.0,
        "label": "Gold · EMA20/50/200 + RSI8",
    },
}


def preset_for(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    return dict(PAIR_PRESETS.get(sym, PAIR_PRESETS["EURUSD"]))


def strategy_info(strategy_id: str) -> dict[str, Any]:
    return STRATEGIES.get(strategy_id, STRATEGIES["EMA_RSI_SCALP"])
