"""Tests for scale-in paper demo accounts (3 legs, isolated from standard demos)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import OrderRequest, OrderStatus, Side, Signal, Tick, utcnow
from app.paper_accounts.registry import PaperAccountRegistry
from app.risk.scale_in import (
    mark_signal_entry,
    plan_scale_in_entry,
    scale_in_lots,
    signal_entry_cooldown_ok,
)


@pytest.fixture
def scale_in_engine(tmp_path: Path):
    store = tmp_path / "paper_accounts.json"
    settings = Settings(max_open_positions=1, scale_in_max_legs=3, scale_in_step_pips=18.0)
    reg = PaperAccountRegistry(settings, store_path=store)
    acct = reg.create(
        deposit=1000.0,
        label="Scale-in test",
        follow_auto=True,
        scale_in_mode=True,
    )
    acct.code = "SCALE3"
    reg.save()
    engine = TradingEngine(settings)
    engine.accounts = reg
    return engine, acct


def test_scale_in_lots_tiers():
    settings = Settings(scale_in_base_lot_per_1k=0.01)
    assert scale_in_lots(1000.0, 1, settings) == 0.01
    assert scale_in_lots(1000.0, 2, settings) == 0.02
    assert scale_in_lots(1000.0, 3, settings) == 0.03
    assert scale_in_lots(2500.0, 1, settings) == 0.02


@pytest.mark.asyncio
async def test_standard_account_still_blocks_second_position(scale_in_engine):
    engine, acct = scale_in_engine
    regular = engine.accounts.create(deposit=1000.0, label="Regular demo", follow_auto=True)
    tick = Tick(symbol="XAUUSD", bid=4500.0, ask=4500.3, mid=4500.15, timestamp=utcnow())
    regular.broker._last_ticks["XAUUSD"] = tick
    req1 = OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.01)
    await engine._execute(req1, tick=tick, account=regular)
    req2 = OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.01)
    order2 = await engine._execute(req2, tick=tick, account=regular)
    assert order2.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_scale_in_account_allows_three_legs(scale_in_engine):
    engine, acct = scale_in_engine
    assert engine._is_scale_in_account(acct)
    for leg, bid in enumerate([4500.0, 4498.0, 4496.0], start=1):
        tick = Tick(symbol="XAUUSD", bid=bid, ask=bid + 0.3, mid=bid + 0.15, timestamp=utcnow())
        acct.broker._last_ticks["XAUUSD"] = tick
        plan = plan_scale_in_entry(
            symbol="XAUUSD",
            side=Side.BUY,
            balance=1000.0,
            open_positions=acct.broker.open_positions(),
            tick=tick,
            settings=engine.settings,
            require_depth=leg > 1,
        )
        assert plan.allowed, plan.reason
        assert plan.leg == leg
        req = OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=plan.lots,
            setup_id=plan.setup_id,
            leg_index=plan.leg,
        )
        order = await engine._execute(req, tick=tick, account=acct)
        assert order.status == OrderStatus.FILLED
        assert order.lots == scale_in_lots(1000.0, leg, engine.settings)

    assert len(acct.broker.open_positions()) == 3


def test_create_scale_in_demo_api_shape(scale_in_engine):
    engine, _ = scale_in_engine
    payload = engine.create_scale_in_demo_account(deposit=1000.0)
    assert payload["ok"] is True
    assert payload["account"]["scale_in_mode"] is True


@pytest.mark.asyncio
async def test_scale_in_leg1_not_blocked_by_engine_cooldown(scale_in_engine):
    """SCALE3 leg 1 must fill even when DDDC3D/global cooldown is armed."""
    engine, acct = scale_in_engine
    engine._entry_cooldown_until = time.time() + 600
    tick = Tick(symbol="XAUUSD", bid=4500.0, ask=4500.3, mid=4500.15, timestamp=utcnow())
    acct.broker._last_ticks["XAUUSD"] = tick
    signal = Signal(
        strategy="AI_ML/EMA_RSI_Scalp",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.9,
        reason="test signal",
        stop_loss=4488.0,
        take_profit=4522.5,
        timestamp=utcnow(),
    )
    await engine._handle_scale_in_signal_for_account(signal, tick, account=acct)
    assert len(acct.broker.open_positions()) == 1
    assert acct.journal.list(10)[0].status.value == "OPEN"


@pytest.mark.asyncio
async def test_scale_in_pullback_adds_share_anchor_stops(scale_in_engine):
    """Legs 2–3 reuse leg-1 SL/TP and enter on 18p pullback."""
    engine, acct = scale_in_engine
    tick1 = Tick(symbol="XAUUSD", bid=4500.0, ask=4500.3, mid=4500.15, timestamp=utcnow())
    acct.broker._last_ticks["XAUUSD"] = tick1
    signal = Signal(
        strategy="AI_ML/EMA_RSI_Scalp",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.9,
        reason="test",
        stop_loss=4488.0,
        take_profit=4522.5,
        timestamp=utcnow(),
    )
    await engine._handle_scale_in_signal_for_account(signal, tick1, account=acct)
    anchor = acct.broker.open_positions()[0]
    assert anchor.stop_loss == 4488.0
    assert anchor.take_profit == 4522.5

    tick2 = Tick(symbol="XAUUSD", bid=4498.0, ask=4498.3, mid=4498.15, timestamp=utcnow())
    acct.broker._last_ticks["XAUUSD"] = tick2
    from app.risk import scale_in as si

    si._last_leg_add_at[acct.id] = 0.0
    await engine._maybe_scale_in_adds(tick2)
    legs = acct.broker.open_positions()
    assert len(legs) == 2
    assert legs[1].stop_loss == 4488.0
    assert legs[1].take_profit == 4522.5
    assert legs[1].leg_index == 2


def test_signal_entry_cooldown_is_per_account():
    assert signal_entry_cooldown_ok("acct-a", 300.0)
    mark_signal_entry("acct-a")
    assert not signal_entry_cooldown_ok("acct-a", 300.0)
    assert signal_entry_cooldown_ok("acct-b", 300.0)


@pytest.mark.asyncio
async def test_scale_in_account_respects_daily_loss_kill_switch(tmp_path: Path):
    """SCALE3 must stop opening new legs once the daily loss limit is hit —
    previously scale-in accounts bypassed max_daily_loss_pct entirely."""
    store = tmp_path / "paper_accounts.json"
    settings = Settings(
        max_open_positions=1,
        scale_in_max_legs=3,
        scale_in_step_pips=18.0,
        max_daily_loss_pct=1.0,
    )
    reg = PaperAccountRegistry(settings, store_path=store)
    acct = reg.create(
        deposit=1000.0,
        label="Scale-in daily loss test",
        follow_auto=True,
        scale_in_mode=True,
    )
    reg.save()
    engine = TradingEngine(settings)
    engine.accounts = reg

    # Simulate a realized loss exceeding the 1% daily limit ($1000 * 1% = $10)
    acct.risk.record_realized_pnl(-15.0)
    assert acct.risk.daily_loss_hit() is True

    tick = Tick(symbol="XAUUSD", bid=4500.0, ask=4500.3, mid=4500.15, timestamp=utcnow())
    acct.broker._last_ticks["XAUUSD"] = tick
    order = await engine._execute(
        OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.01),
        tick=tick,
        account=acct,
    )
    assert order.status == OrderStatus.REJECTED
    assert "daily loss" in (order.reject_reason or "").lower()
    assert len(acct.broker.open_positions()) == 0
