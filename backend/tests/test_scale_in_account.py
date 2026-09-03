"""Tests for scale-in paper demo accounts (3 legs, isolated from standard demos)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import OrderRequest, OrderStatus, Position, PositionStatus, Side, Tick, utcnow
from app.paper_accounts.registry import PaperAccountRegistry
from app.risk.scale_in import plan_scale_in_entry, scale_in_lots, scale_in_step_pips_for_session


@pytest.fixture
def scale_in_engine(tmp_path: Path):
    store = tmp_path / "paper_accounts.json"
    settings = Settings(
        max_open_positions=1,
        scale_in_max_legs=3,
        scale_in_step_pips_asia=75.0,
        scale_in_step_pips_night=125.0,
    )
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


def test_scale_in_step_pips_asia_vs_night():
    settings = Settings(scale_in_step_pips_asia=75.0, scale_in_step_pips_night=125.0)
    asia_ts = datetime(2026, 3, 2, 3, 0, tzinfo=timezone.utc)  # PH 11AM → asia
    night_ts = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)  # PH 10PM → SMC
    assert scale_in_step_pips_for_session(settings, asia_ts) == 75.0
    assert scale_in_step_pips_for_session(settings, night_ts) == 125.0


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
async def test_scale_in_account_allows_three_legs_asia_spacing(scale_in_engine):
    engine, acct = scale_in_engine
    assert engine._is_scale_in_account(acct)
    asia_ts = datetime(2026, 3, 2, 3, 0, tzinfo=timezone.utc)
    # 75 pips × 0.1 pip size = 7.5 points between legs
    for leg, bid in enumerate([4500.0, 4492.0, 4484.0], start=1):
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
            at=asia_ts,
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


def test_scale_in_blocks_leg2_until_night_spacing(scale_in_engine):
    engine, _ = scale_in_engine
    night_ts = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)
    leg1 = Position(
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.01,
        entry_price=4500.0,
        leg_index=1,
        setup_id="setup123",
        status=PositionStatus.OPEN,
    )
    tick_shallow = Tick(symbol="XAUUSD", bid=4492.5, ask=4492.8, mid=4492.65, timestamp=utcnow())
    blocked = plan_scale_in_entry(
        symbol="XAUUSD",
        side=Side.BUY,
        balance=1000.0,
        open_positions=[leg1],
        tick=tick_shallow,
        settings=engine.settings,
        require_depth=True,
        at=night_ts,
    )
    assert not blocked.allowed
    assert "125" in blocked.reason


def test_create_scale_in_demo_api_shape(scale_in_engine):
    engine, _ = scale_in_engine
    payload = engine.create_scale_in_demo_account(deposit=1000.0)
    assert payload["ok"] is True
    assert payload["account"]["scale_in_mode"] is True
