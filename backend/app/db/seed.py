"""Seed core XAUUSD scalping strategies (EMA+RSI + SMC)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.models import StrategyRow
from app.db.session import db_enabled, session_scope

log = logging.getLogger(__name__)

SEED_STRATEGIES: list[dict] = [
    {
        "name": "AI_ML",
        "timeframe": "M5",
        "description": (
            "AI & Machine Learning stack: session child setup "
            "(EMA_RSI / SMC / VWAP) + sklearn win-probability filter"
        ),
        "parameters": {
            "engine": "AI & Machine Learning",
            "online_model": "SGDClassifier(log_loss)",
            "batch_model": "LogisticRegression",
            "session_children": {
                "asia": "EMA_RSI_Scalp",
                "london": "EMA_RSI_Scalp",
                "london_wind_down": "EMA_RSI_Scalp",
                "london_close": "EMA_RSI_Scalp",
                "london_ny_overlap": "Liquidity_Sweep_SMC",
                "new_york": "EMA_VWAP_Scalp",
                "off_hours": "EMA_RSI_Scalp",
            },
            "actions": ["TAKE", "CAUTION", "SKIP"],
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "EMA_RSI_Scalp",
        "timeframe": "M5",
        "description": "EMA 200 trend + EMA 20/50 retest + RSI 14 + engulfing/pin bar",
        "parameters": {
            "ema_trend": 200,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_buy_zone": [38, 52],
            "rsi_sell_zone": [38, 62],
            "patterns": ["engulfing", "pin_bar"],
            "reward_r": 2.0,
            "min_stop_atr": 1.15,
            "min_tp_atr": 2.3,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "EMA_VWAP_Scalp",
        "timeframe": "M5",
        "description": "9/21 EMA crossover + session VWAP filter · swing SL · 2R TP",
        "parameters": {
            "ema_fast": 9,
            "ema_slow": 21,
            "reward_r": 2.0,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "Liquidity_Sweep_SMC",
        "timeframe": "M5",
        "description": "Asia/PDH-PDL sweep + MSS/ChoCH + FVG/OB retest entry",
        "parameters": {
            "asia_session_utc": ["00:00", "07:00"],
            "liquidity": ["ASIAN_HIGH", "ASIAN_LOW", "PDH", "PDL", "SWING_HIGH", "SWING_LOW"],
            "structure": ["MSS", "ChoCH"],
            "entry_zones": ["SWEEP", "RETEST", "FVG", "ORDER_BLOCK"],
            "require_sweep": True,
            "sweep_lookback_bars": 36,
            "sweep_valid_bars": 18,
            "reward_r": 2.0,
            "min_stop_atr": 2.5,
            "min_tp_atr": 5.0,
            "swing_lookback": 6,
            "atr_pad": 0.55,
            "max_trades_per_day": 4,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
]


def seed_strategies(*, force_update: bool = False) -> dict:
    """Insert default strategies if missing. Safe to call on every boot."""
    if not db_enabled():
        return {"ok": False, "skipped": True, "reason": "db_disabled"}

    inserted = 0
    updated = 0
    with session_scope() as session:
        for spec in SEED_STRATEGIES:
            existing = session.scalar(
                select(StrategyRow).where(StrategyRow.name == spec["name"])
            )
            if existing is None:
                session.add(
                    StrategyRow(
                        name=spec["name"],
                        timeframe=spec["timeframe"],
                        description=spec["description"],
                        parameters=spec["parameters"],
                        is_active=True,
                    )
                )
                inserted += 1
            elif force_update:
                existing.timeframe = spec["timeframe"]
                existing.description = spec["description"]
                existing.parameters = spec["parameters"]
                existing.is_active = True
                updated += 1
    log.info("strategy seed: inserted=%s updated=%s", inserted, updated)
    return {"ok": True, "inserted": inserted, "updated": updated}
