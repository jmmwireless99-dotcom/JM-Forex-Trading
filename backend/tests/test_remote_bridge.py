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
            mt_symbol="GOLD24-7#",
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
            "ticks": "GOLD24-7#,4585.50,4585.80,2026-08-28 10:00:00\n",
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
async def test_remote_sync_rejects_bad_token(remote_client):
    client, _ = remote_client
    res = await client.post(
        "/api/mt/remote/sync",
        json={"token": "wrong-token-xx", "status": "ok,1,1,0,t\n"},
    )
    assert res.status_code == 403
