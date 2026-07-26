"""Hourly session auto-transfer — kusang lilipat each UTC hour."""

from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import Tick


def _tick(hour: int, minute: int = 0) -> Tick:
    ts = datetime(2026, 7, 23, hour, minute, tzinfo=timezone.utc)
    return Tick(symbol="XAUUSD", bid=4000.0, ask=4000.2, mid=4000.1, timestamp=ts)


@pytest.mark.asyncio
async def test_hourly_transfer_switches_london_to_smc():
    engine = TradingEngine(
        Settings(
            tick_interval_seconds=0.05,
            auto_strategy=True,
            auto_transfer_interval_seconds=3600,
            paper_sync_live_gold=False,
            execution_mode="paper",
        )
    )
    engine.auto_enabled = True
    # Seed as if we already transferred for London hour 10
    engine._last_transfer_hour_key = "2026-07-23T10"
    engine._last_hourly_transfer_at = 1.0
    engine._park_strategy("London_Judas_Sweep", note="seed london")

    switched = await engine._run_hourly_auto_transfer(_tick(13, 0))
    assert switched is True
    assert engine.active_name == "Liquidity_Sweep_SMC"
    assert engine._last_transfer_hour_key == "2026-07-23T13"
    assert "Liquidity_Sweep_SMC" in (engine._last_transfer_note or "")
    assert "13:00" in (engine._last_transfer_note or "")
    auto = engine.auto_status()
    assert auto["hourly_transfer"] is True
    assert auto["transfer_interval_seconds"] == 3600


@pytest.mark.asyncio
async def test_hourly_transfer_switches_smc_to_trend_breakout():
    engine = TradingEngine(
        Settings(
            tick_interval_seconds=0.05,
            auto_strategy=True,
            auto_transfer_interval_seconds=3600,
            paper_sync_live_gold=False,
            execution_mode="paper",
        )
    )
    engine.auto_enabled = True
    engine._last_transfer_hour_key = "2026-07-23T15"
    engine._last_hourly_transfer_at = 1.0
    engine._park_strategy("Liquidity_Sweep_SMC", note="seed smc")

    switched = await engine._run_hourly_auto_transfer(_tick(16, 0))
    assert switched is True
    assert engine.active_name == "Trend_Breakout_ATR"


@pytest.mark.asyncio
async def test_same_hour_does_not_retransfer():
    engine = TradingEngine(
        Settings(
            tick_interval_seconds=0.05,
            auto_strategy=True,
            auto_transfer_interval_seconds=3600,
            paper_sync_live_gold=False,
            execution_mode="paper",
        )
    )
    engine.auto_enabled = True
    engine._last_transfer_hour_key = "2026-07-23T13"
    engine._last_hourly_transfer_at = 9_999_999_999.0  # far future = interval not elapsed
    engine._park_strategy("Liquidity_Sweep_SMC", note="seed smc")

    switched = await engine._run_hourly_auto_transfer(_tick(13, 30))
    assert switched is False
    assert engine.active_name == "Liquidity_Sweep_SMC"
