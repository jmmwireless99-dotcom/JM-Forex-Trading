"""Tests for remote MT5 bridge sync API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_engine
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def remote_client(tmp_path):
    reset_engine(
        Settings(
            tick_interval_seconds=0.05,
            auto_strategy=False,
            execution_mode="mt5",
            mt5_bridge_dir=str(tmp_path / "bridge"),
            mt_remote_bridge=True,
            mt_bridge_token="test-bridge-token",
            mt5_demo_account_code="ABC123",
            mt_symbol="GOLD#",
        )
    )
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, tmp_path / "bridge"
    await reset_engine(Settings()).stop()


@pytest.mark.asyncio
async def test_remote_sync_writes_files(remote_client):
    client, bridge_dir = remote_client
    res = await client.post(
        "/api/mt/remote/sync",
        json={
            "token": "test-bridge-token",
            "status": "ok,1000.00,1000.00,0,2026-08-28 10:00:00\n",
            "ticks": "GOLD#,4585.50,4585.80,2026-08-28 10:00:00\n",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "jm_status.csv" in body["written"]
    assert (bridge_dir / "jm_status.csv").exists()

    mt = await client.get("/api/mt/status")
    assert mt.status_code == 200
    assert mt.json()["configured"] is True
    assert mt.json()["online"] is True


@pytest.mark.asyncio
async def test_remote_sync_pushes_mt_demo_account(remote_client):
    client, bridge_dir = remote_client
    reset_engine(
        Settings(
            tick_interval_seconds=0.05,
            auto_strategy=False,
            execution_mode="paper",
            mt5_bridge_dir=str(bridge_dir),
            mt_remote_bridge=True,
            mt_bridge_token="test-bridge-token",
            mt5_demo_account_code="ABC123",
            mt_symbol="GOLD#",
        )
    )
    from app.api.deps import get_engine
    from app.paper_accounts.registry import PaperAccountRegistry

    engine = get_engine()
    store = bridge_dir.parent / "accounts.json"
    reg = PaperAccountRegistry(engine.settings, store_path=store)
    acct = reg.create(deposit=500.0, label="XM MT5 Demo", follow_auto=False)
    acct.code = "ABC123"
    engine.accounts = reg

    events: list[str] = []

    async def capture(msg):
        if msg.get("event") == "account":
            events.append(msg["data"].get("account_code", ""))

    engine.subscribe(capture)
    res = await client.post(
        "/api/mt/remote/sync",
        json={
            "token": "test-bridge-token",
            "status": "ok,1000.00,1005.50,0,2026-08-28 10:00:00\n",
        },
    )
    assert res.status_code == 200
    assert events == ["ABC123"]
    payload = engine.account_payload(acct)
    assert payload["balance"] == 1000.0
    assert payload["mt5_only"] is True


@pytest.mark.asyncio
async def test_remote_command_endpoint(remote_client):
    client, bridge_dir = remote_client
    (bridge_dir / "jm_command.csv").write_text(
        "id,action,symbol,side,lots,sl,tp,comment\n"
        "abc123,OPEN,GOLD#,BUY,0.01,4580,4610,manual\n"
    )
    res = await client.get("/api/mt/remote/command?token=test-bridge-token")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["pending"] is True
    assert "GOLD#" in body["command"]


@pytest.mark.asyncio
async def test_remote_sync_rejects_bad_token(remote_client):
    client, _ = remote_client
    res = await client.post(
        "/api/mt/remote/sync",
        json={"token": "wrong-token-xx", "status": "ok,1,1,0,t\n"},
    )
    assert res.status_code == 403
