from datetime import datetime, timezone

import pytest

from app.api.deps import reset_engine
from app.core.config import Settings, get_settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import OrderRequest, Side, Tick


def _seed_tick(engine: TradingEngine, price: float = 2350.0) -> Tick:
    tick = Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc),
    )
    engine._recent_ticks["XAUUSD"] = tick
    engine.paper.update_tick(tick)
    return tick


@pytest.mark.asyncio
async def test_manual_buy_attaches_auto_stops():
    get_settings.cache_clear()
    engine = TradingEngine(
        Settings(auto_strategy=False, default_strategy="manual_only", news_filter=False)
    )
    _seed_tick(engine)
    order = await engine.manual_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            strategy="manual",
            attach_stops=True,
        )
    )
    assert order.status.value == "FILLED"
    assert order.stop_loss is not None
    assert order.take_profit is not None
    assert order.stop_loss < order.fill_price
    assert order.take_profit > order.fill_price
    pos = engine.open_positions()[0]
    assert pos.stop_loss == order.stop_loss
    assert pos.take_profit == order.take_profit
    await engine.stop()
    reset_engine(Settings())


@pytest.mark.asyncio
async def test_manual_sell_without_stops_then_attach():
    get_settings.cache_clear()
    engine = TradingEngine(
        Settings(auto_strategy=False, default_strategy="manual_only", news_filter=False)
    )
    _seed_tick(engine, 2400.0)
    order = await engine.manual_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.SELL,
            lots=0.01,
            strategy="manual",
            attach_stops=False,
        )
    )
    assert order.status.value == "FILLED"
    assert order.stop_loss is None
    assert order.take_profit is None
    pos = engine.open_positions()[0]
    updated = await engine.set_position_stops(pos.id, auto=True)
    assert updated is not None
    assert updated.stop_loss is not None
    assert updated.take_profit is not None
    assert updated.stop_loss > updated.entry_price  # sell SL above
    assert updated.take_profit < updated.entry_price
    await engine.stop()
    reset_engine(Settings())


@pytest.mark.asyncio
async def test_api_manual_order_and_stops():
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    get_settings.cache_clear()
    reset_engine(Settings(tick_interval_seconds=0.05, news_filter=False))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from app.api.deps import get_engine

        eng = get_engine()
        _seed_tick(eng, 2355.0)

        created = await client.post(
            "/api/accounts",
            json={"deposit": 1000, "label": "manual-order-test"},
        )
        assert created.status_code == 200
        acct_body = created.json()
        headers = {
            "X-JM-Account-Id": acct_body["account"]["account_id"],
            "X-JM-Account-Token": acct_body["token"],
        }
        acct = eng.accounts.require(
            acct_body["account"]["account_id"], acct_body["token"]
        )

        res = await client.post(
            "/api/orders",
            headers=headers,
            json={
                "symbol": "XAUUSD",
                "side": "BUY",
                "lots": 0.01,
                "auto_stops": True,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "FILLED"
        assert body["stop_loss"] is not None
        assert body["take_profit"] is not None
        assert body["auto_stops"] is True

        res2 = await client.post(
            "/api/orders",
            headers=headers,
            json={
                "symbol": "XAUUSD",
                "side": "SELL",
                "lots": 0.01,
                "auto_stops": True,
            },
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "REJECTED"

        opens = (await client.get("/api/positions", headers=headers)).json()["open"]
        assert len(opens) == 1
        pid = opens[0]["id"]

        pos = acct.broker.open_positions()[0]
        pos.stop_loss = None
        pos.take_profit = None

        res3 = await client.post(
            f"/api/positions/{pid}/stops",
            headers=headers,
            json={"auto": True},
        )
        assert res3.status_code == 200
        stops = res3.json()
        assert stops["stop_loss"] is not None
        assert stops["take_profit"] is not None

    await reset_engine(Settings()).stop()
