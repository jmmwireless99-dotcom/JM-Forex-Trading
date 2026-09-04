import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_engine
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client():
    reset_engine(Settings(tick_interval_seconds=0.05, auto_strategy=False))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = reset_engine(Settings())
    await engine.stop()


async def _make_account(client, *, deposit=1000.0, label="Test demo"):
    res = await client.post(
        "/api/accounts",
        json={"deposit": deposit, "label": label, "follow_auto": True},
    )
    assert res.status_code == 200
    body = res.json()
    headers = {
        "X-JM-Account-Id": body["account"]["account_id"],
        "X-JM-Account-Token": body["token"],
    }
    return body, headers


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
    assert "AI_ML" in names
    assert "EMA_RSI_Scalp" in names
    assert "EMA_VWAP_Scalp" in names
    assert "Liquidity_Sweep_SMC" in names
    assert "NewsBreakout" in names
    assert "London_Judas_Sweep" not in names

    res = await client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "paper"
    assert body["active_strategy"] == "AI_ML"
    assert body["symbols"] == ["XAUUSD"]


@pytest.mark.asyncio
async def test_desk_endpoint(client):
    res = await client.get("/api/desk")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "scalp_desk"
    assert data["recommended_strategy"] == "AI_ML"
    assert data["recommended_london"] == "Stand aside"
    assert data["recommended_asia"] == "AI_ML → EMA_RSI_Scalp"
    assert data["symbol"] == "XAUUSD"
    assert "session" in data and "news" in data
    assert data["auto"]["enabled"] is False
    assert len(data["indicators"]) >= 1
    assert len(data["strategy_details"]) == 5
    aiml = next(s for s in data["strategy_details"] if s["id"] == "AI_ML")
    assert "Machine Learning" in aiml["name"]


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
async def test_account_requires_headers(client):
    res = await client.get("/api/account")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_account_endpoint(client):
    created, headers = await _make_account(client, deposit=10000.0)
    res = await client.get("/api/account", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["balance"] == 10000.0
    assert data["currency"] == "USD"
    assert data["deposit"] == 10000.0
    assert data["paper"] is True
    assert data["account_id"] == created["account"]["account_id"]
    assert "capital" in data
    assert data["capital"]["suggested_lots"] >= 0.01


@pytest.mark.asyncio
async def test_paper_deposit_changes_capital(client):
    _, headers = await _make_account(client, deposit=1000.0)
    res = await client.post(
        "/api/account/deposit",
        json={"amount": 500, "reset": True},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["account"]["balance"] == 500.0
    assert body["account"]["deposit"] == 500.0
    assert body["capital"]["deposit"] == 500.0
    assert body["capital"]["risk_per_trade_usd"] == 2.5  # 0.5% of 500

    preview = await client.get("/api/account/capital?amount=1000", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["deposit"] == 1000.0
    assert preview.json()["risk_per_trade_usd"] == 5.0

    # Live account still at 500 until applied
    acc = await client.get("/api/account", headers=headers)
    assert acc.json()["deposit"] == 500.0


@pytest.mark.asyncio
async def test_paper_deposit_keeps_trade_history(client):
    _, headers = await _make_account(client, deposit=1000.0)
    await client.post("/api/engine/start")
    import asyncio

    await asyncio.sleep(0.15)
    order = await client.post(
        "/api/orders",
        headers=headers,
        json={
            "symbol": "XAUUSD",
            "side": "BUY",
            "lots": 0.01,
            "auto_stops": True,
            "comment": "deposit-history-test",
        },
    )
    assert order.status_code == 200
    before = await client.get("/api/trades?limit=50", headers=headers)
    before_n = before.json()["summary"]["total"]
    assert before_n >= 1

    res = await client.post(
        "/api/account/deposit",
        json={"amount": 2500, "reset": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["account"]["deposit"] == 2500.0
    after = await client.get("/api/trades?limit=50", headers=headers)
    assert after.json()["summary"]["total"] >= before_n


@pytest.mark.asyncio
async def test_accounts_are_isolated(client):
    a, ha = await _make_account(client, deposit=500.0, label="Client A")
    b, hb = await _make_account(client, deposit=2000.0, label="Client B")
    assert a["account"]["account_id"] != b["account"]["account_id"]

    await client.post("/api/engine/start")
    import asyncio

    await asyncio.sleep(0.15)
    order = await client.post(
        "/api/orders",
        headers=ha,
        json={"symbol": "XAUUSD", "side": "BUY", "lots": 0.01, "auto_stops": True},
    )
    assert order.status_code == 200

    trades_a = await client.get("/api/trades", headers=ha)
    trades_b = await client.get("/api/trades", headers=hb)
    assert trades_a.json()["summary"]["total"] >= 1
    assert trades_b.json()["summary"]["total"] == 0

    acc_a = await client.get("/api/account", headers=ha)
    acc_b = await client.get("/api/account", headers=hb)
    assert acc_a.json()["deposit"] == 500.0
    assert acc_b.json()["deposit"] == 2000.0
    assert acc_a.json()["open_positions"] >= 1
    assert acc_b.json()["open_positions"] == 0

    # Wrong token rejected
    bad = await client.get(
        "/api/account",
        headers={
            "X-JM-Account-Id": a["account"]["account_id"],
            "X-JM-Account-Token": "wrong-token",
        },
    )
    assert bad.status_code == 403


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

    res = await client.post("/api/strategies/active", json={"name": "manual_only"})
    assert res.status_code == 200
    body = res.json()
    assert body["active_strategy"] == "manual_only"


@pytest.mark.asyncio
async def test_account_login(client):
    body, headers = await _make_account(client, label="Login test")
    code = body["account"]["account_code"]
    token = body["token"]

    res = await client.post("/api/accounts/login", json={"code": code, "token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["account_code"] == code
    assert data["account_id"] == body["account"]["account_id"]
    assert data["account"]["account_code"] == code

    res = await client.post("/api/accounts/login", json={"code": code, "token": "wrong-token"})
    assert res.status_code == 403

    res = await client.post("/api/accounts/login", json={"code": "ZZZZZZ", "token": token})
    assert res.status_code == 404


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
        "AI_ML",
        "EMA_RSI_Scalp",
        "EMA_VWAP_Scalp",
        "Liquidity_Sweep_SMC",
    }
    assert body["active_strategy"] == body["to"]
    assert "message" in body
