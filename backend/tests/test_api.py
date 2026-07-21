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
    assert "manual_only" in names
    assert "EMA_RSI_Scalp" in names
    assert "Liquidity_Sweep_SMC" in names
    assert "London_Judas_Sweep" in names

    res = await client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "paper"
    assert body["active_strategy"] == "manual_only"
    assert body["symbols"] == ["XAUUSD"]


@pytest.mark.asyncio
async def test_desk_endpoint(client):
    res = await client.get("/api/desk")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "scalp_desk"
    assert data["recommended_strategy"] == "London_Judas_Sweep"
    assert data["recommended_london"] == "London_Judas_Sweep"
    assert data["recommended_asia"] == "EMA_RSI_Scalp"
    assert data["symbol"] == "XAUUSD"
    assert "session" in data and "news" in data
    assert data["auto"]["enabled"] is False
    assert len(data["indicators"]) >= 1
    assert len(data["strategy_details"]) == 4
    london = next(s for s in data["strategy_details"] if s["id"] == "London_Judas_Sweep")
    assert london["order_type"] == "LIMIT"
    assert len(london["entry_rules"]) >= 4


@pytest.mark.asyncio
async def test_auto_endpoint(client):
    res = await client.get("/api/auto")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert len(data["schedule"]) >= 1


@pytest.mark.asyncio
async def test_mt4_status_unconfigured(client):
    res = await client.get("/api/mt4/status")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False
    assert data["online"] is False


@pytest.mark.asyncio
async def test_account_endpoint(client):
    res = await client.get("/api/account")
    assert res.status_code == 200
    data = res.json()
    assert data["balance"] == 10000.0
    assert data["currency"] == "USD"


@pytest.mark.asyncio
async def test_apply_strategy_switches(client):
    res = await client.post("/api/strategies/active", json={"name": "EMA_RSI_Scalp"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["active_strategy"] == "EMA_RSI_Scalp"
    assert body["auto"]["enabled"] is False

    res = await client.post("/api/strategies/active", json={"name": "Liquidity_Sweep_SMC"})
    assert res.status_code == 200
    body = res.json()
    assert body["active_strategy"] == "Liquidity_Sweep_SMC"

    res = await client.post("/api/strategies/active", json={"name": "London_Judas_Sweep"})
    assert res.status_code == 200
    assert res.json()["active_strategy"] == "London_Judas_Sweep"

    res = await client.post("/api/strategies/active", json={"name": "manual_only"})
    assert res.status_code == 200
    body = res.json()
    assert body["active_strategy"] == "manual_only"


@pytest.mark.asyncio
async def test_auto_transfer_session_follow(client):
    res = await client.get("/api/strategies/recommended")
    assert res.status_code == 200
    rec = res.json()
    assert "session" in rec
    assert "reason" in rec

    res = await client.post("/api/strategies/auto-transfer")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["auto_enabled"] is True
    assert body["to"] in {
        "manual_only",
        "EMA_RSI_Scalp",
        "London_Judas_Sweep",
        "Liquidity_Sweep_SMC",
    }
    assert body["active_strategy"] == body["to"]
