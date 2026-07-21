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
    assert "auto_gold" in names
    assert "gold_confluence" in names
    assert "gold_atr_trend" in names
    assert "asia_m5_sr_scalp" in names
    assert "asia_sr_scalp" in names
    assert "asia_range_scalp" in names
    assert "gold_sr_scalp" in names
    assert "ema_crossover" in names

    res = await client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "paper"
    assert body["active_strategy"].startswith("auto_gold")
    assert body["symbols"] == ["XAUUSD"]


@pytest.mark.asyncio
async def test_desk_endpoint(client):
    res = await client.get("/api/desk")
    assert res.status_code == 200
    data = res.json()
    assert data["recommended_strategy"] == "auto_gold"
    assert data["recommended_asia"] == "asia_m5_sr_scalp"
    assert data["recommended_london"] == "gold_confluence"
    assert data["recommended_overlap"] == "gold_atr_trend"
    assert data["symbol"] == "XAUUSD"
    assert "session" in data and "news" in data
    assert data["auto"]["enabled"] is True
    assert len(data["indicators"]) >= 4


@pytest.mark.asyncio
async def test_auto_endpoint(client):
    res = await client.get("/api/auto")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert len(data["schedule"]) >= 4


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
async def test_apply_strategy_switches_and_disables_auto(client):
    res = await client.post("/api/strategies/active", json={"name": "asia_range_scalp"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["active_strategy"] == "asia_range_scalp"
    assert body["auto"]["enabled"] is False

    res = await client.post("/api/strategies/active", json={"name": "auto_gold"})
    assert res.status_code == 200
    body = res.json()
    assert body["active_strategy"].startswith("auto_gold")
    assert body["auto"]["enabled"] is True


@pytest.mark.asyncio
async def test_auto_transfer_enables_session_strategy(client):
    # Leave manual mode first
    await client.post("/api/strategies/active", json={"name": "ema_crossover"})
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
    assert body["transferred"] is True
    assert body["active_strategy"].startswith("auto_gold")
    assert body["to"] in {
        "gold_confluence",
        "gold_atr_trend",
        "gold_sr_scalp",
        "asia_m5_sr_scalp",
        "asia_sr_scalp",
        "asia_range_scalp",
    }