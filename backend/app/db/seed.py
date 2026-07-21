"""Seed core XAUUSD scalping strategies (EMA+RSI + SMC)."""

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
        "description": "EMA 200 trend + EMA 20/50 retest + RSI 14 + engulfing/pin bar",
        "parameters": {
            "ema_trend": 200,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_buy_zone": [40, 50],
            "rsi_sell_zone": [50, 60],
            "patterns": ["engulfing", "pin_bar"],
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
            "liquidity": ["ASIAN_HIGH", "ASIAN_LOW", "PDH", "PDL"],
            "structure": ["MSS", "ChoCH"],
            "entry_zones": ["FVG", "ORDER_BLOCK"],
            "require_sweep": True,
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
