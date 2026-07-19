import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_engine
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client():
    reset_engine(Settings(tick_interval_seconds=0.05))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = reset_engine(Settings())
    await engine.stop()


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["service"] == "JM Forex"


@pytest.mark.asyncio
async def test_strategies_and_status(client):
    res = await client.get("/api/strategies")
    names = res.json()["strategies"]
    assert "gold_atr_trend" in names
    assert "ema_crossover" in names

    res = await client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "paper"
    assert body["active_strategy"] == "gold_atr_trend"
    assert body["symbols"] == ["XAUUSD"]


@pytest.mark.asyncio
async def test_account_endpoint(client):
    res = await client.get("/api/account")
    assert res.status_code == 200
    data = res.json()
    assert data["balance"] == 10000.0
    assert data["currency"] == "USD"