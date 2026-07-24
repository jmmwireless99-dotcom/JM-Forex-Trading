"""Seed core XAUUSD scalping strategies (EMA+RSI + SMC + London Judas)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.models import StrategyRow
from app.db.session import db_enabled, session_scope

log = logging.getLogger(__name__)

SEED_STRATEGIES: list[dict] = [
    {
        "name": "EMA_RSI_Scalp",
        "timeframe": "M5",
        "description": (
            "EMA 200 trend + EMA 20/50 retest + RSI 14 + engulfing/pin only "
            "(no soft body) · Asia/NY quality windows"
        ),
        "parameters": {
            "ema_trend": 200,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_buy_zone": [40, 50],
            "rsi_sell_zone": [50, 60],
            "patterns": ["engulfing", "pin_bar"],
            "min_bars_between_signals": 12,
            "reward_r": 2.2,
            "min_stop_atr": 1.5,
            "min_tp_atr": 2.8,
            "allow_soft_confirm": False,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "Liquidity_Sweep_SMC",
        "timeframe": "M5",
        "description": (
            "Asia 00-06 / PDH-PDL / recent swing sweep + MSS + FVG/OB retest "
            "(max 1/day) · London/NY overlap only"
        ),
        "parameters": {
            "asia_session_utc": ["00:00", "06:00"],
            "liquidity": [
                "ASIAN_HIGH",
                "ASIAN_LOW",
                "PDH",
                "PDL",
                "SWING_HIGH",
                "SWING_LOW",
            ],
            "structure": ["MSS"],
            "entry_zones": ["FVG", "ORDER_BLOCK"],
            "require_sweep": True,
            "require_zone_retest": True,
            "require_mss_confirm": True,
            "max_entries_per_day": 1,
            "reward_r": 2.2,
            "min_stop_atr": 1.2,
            "min_tp_atr": 2.5,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "London_Judas_Sweep",
        "timeframe": "M5",
        "description": (
            "London Judas: Asia 00-06 box · prefer sweep 07-09 (entry to 11) · "
            "FVG50 LIMIT · kill 12:00 UTC · MT fills near mid as market"
        ),
        "parameters": {
            "asia_utc": ["00:00", "06:00"],
            "london_entry_utc": ["07:00", "11:00"],
            "sweep_window_utc": ["07:00", "09:00"],
            "kill_pending_utc": "12:00",
            "min_sweep_pips": 80,
            "max_sweep_pips": 300,
            "sl_buffer_pips": 80,
            "max_spread_pips": 35,
            "pip_size": 0.01,
            "entry": "FVG_50_LIMIT",
            "reward_r": 3.0,
            "mt_near_limit_pips": 120,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
]


def seed_params(name: str) -> dict:
    """Return a copy of seed parameters for a strategy name."""
    for spec in SEED_STRATEGIES:
        if spec["name"] == name:
            return dict(spec.get("parameters") or {})
    return {}


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
