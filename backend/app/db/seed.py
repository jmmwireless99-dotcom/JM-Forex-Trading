"""Seed core XAUUSD strategies (EMA · SMC · Judas · Trend Breakout)."""

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
            "Best EMA pullback: EMA200 trend + clear EMA20/50 stack + RSI + "
            "engulf/pin · structure SL beyond EMA50 · R≈2.5 TP · Asia session"
        ),
        "parameters": {
            "ema_trend": 200,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_buy_zone": [38, 55],
            "rsi_sell_zone": [45, 62],
            "patterns": ["engulfing", "pin_bar"],
            "min_bars_between_signals": 5,
            "reward_r": 2.5,
            "min_stop_atr": 1.4,
            "min_tp_atr": 3.0,
            "max_stop_atr": 2.6,
            "allow_soft_confirm": True,
            "chart_tf": "M1",
            "signal_tf": "M5",
        },
    },
    {
        "name": "Liquidity_Sweep_SMC",
        "timeframe": "M5",
        "description": (
            "SMC blueprint: PDH/PDL sweep → displacement + MSS → FVG50 LIMIT · "
            "SL beyond sweep wick · TP opposite liq / ≥2.8R · kill zones only"
        ),
        "parameters": {
            "asia_session_utc": ["00:00", "06:00"],
            "kill_zones_utc": [[7, 11], [13, 16]],
            "liquidity": [
                "PDH",
                "PDL",
                "ASIAN_HIGH",
                "ASIAN_LOW",
                "SWING_HIGH",
                "SWING_LOW",
            ],
            "structure": ["MSS", "displacement"],
            "entry_zones": ["FVG", "ORDER_BLOCK"],
            "entry": "FVG_50_LIMIT",
            "require_sweep": True,
            "require_zone_retest": True,
            # Soft paper path: do not stall forever on MSS/ChoCH.
            "require_mss_confirm": False,
            "require_displacement": True,
            "prefer_pdh_pdl": True,
            "use_limit_entry": True,
            "fvg_entry_pct": 0.50,
            "max_entries_per_day": 0,
            "reward_r": 2.8,
            "min_stop_atr": 1.4,
            "min_tp_atr": 3.0,
            "max_stop_atr": 3.2,
            "min_sweep_atr": 0.30,
            "max_sweep_atr": 3.2,
            "min_displacement_atr": 0.35,
            "sl_buffer_atr": 0.40,
            "min_sl_dollars": 1.50,
            "sweep_max_age_bars": 30,
            "mt_near_limit_pips": 120,
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
    {
        "name": "Trend_Breakout_ATR",
        "timeframe": "M5",
        "description": (
            "True trend/breakout + hard SL: Donchian20 close-break · EMA200 filter · "
            "ADX · ATR buffer · R≈2.5 · auto New York (no grid/martingale)"
        ),
        "parameters": {
            "channel_period": 20,
            "ema_trend": 200,
            "adx_period": 14,
            "min_adx": 14,
            "min_break_atr": 0.10,
            "reward_r": 2.5,
            "min_stop_atr": 1.2,
            "min_tp_atr": 2.8,
            "max_stop_atr": 2.8,
            "min_bars_between_signals": 6,
            "kill_zones_utc": [[7, 11], [16, 20]],
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
