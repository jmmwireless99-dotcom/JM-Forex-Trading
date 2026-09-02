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
            "rsi_sell_zone": [48, 62],
            "patterns": ["engulfing", "pin_bar"],
            "reward_r": 2.0,
            "min_stop_atr": 1.15,
            "min_tp_atr": 2.3,
            "asia_use_structure_stops": True,
            "asia_min_stop_atr": 1.45,
            "asia_min_tp_atr": 2.9,
            "asia_structure_atr_pad": 0.4,
            "asia_stop_loss_pips_legacy": 120,
            "asia_take_profit_pips_legacy": 225,
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
            "asia_session_utc": ["23:00", "13:00"],
            "liquidity": ["ASIAN_HIGH", "ASIAN_LOW", "PDH", "PDL", "SWING_HIGH", "SWING_LOW"],
            "structure": ["MSS", "ChoCH"],
            "entry_zones": ["SWEEP", "RETEST", "FVG", "ORDER_BLOCK"],
            "require_sweep": True,
            "sweep_lookback_bars": 36,
            "sweep_valid_bars": 18,
            "reward_r": 2.0,
            "min_stop_atr": 3.0,
            "min_tp_atr": 6.0,
            "swing_lookback": 8,
            "atr_pad": 0.65,
            "vol_adaptive_stops": True,
            "vol_mult_max": 1.75,
            "max_trades_per_day": 4,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "NewsBreakout",
        "timeframe": "M5",
        "description": (
            "Post-release momentum on high-impact USD news days "
            "(NFP, CPI, FOMC, Core PCE) — auto-runs instead of AI_ML"
        ),
        "parameters": {
            "events": ["NFP", "CPI", "FOMC", "Core PCE"],
            "post_release_window_min": [5, 60],
            "min_stop_atr": 3.0,
            "min_tp_atr": 6.0,
            "reward_r": 2.0,
            "max_trades_per_day": 2,
            "require_retest": True,
            "retest_valid_bars": 6,
            "retest_pad_atr": 0.35,
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
