"""Account profile / login — history must never reset."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_engine
from app.core.config import Settings
from app.main import create_app
from app.models.domain import Side, TradeLog, TradeStatus, utcnow
from app.paper_accounts.security import hash_password, verify_password


@pytest.fixture
async def client():
    reset_engine(Settings(tick_interval_seconds=0.05, auto_strategy=False))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = reset_engine(Settings())
    await engine.stop()


def test_password_hash_roundtrip():
    stored = hash_password("secret1")
    assert verify_password("secret1", stored)
    assert not verify_password("wrong", stored)


@pytest.mark.asyncio
async def test_register_login_profile_password_keeps_history(client):
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    res = await client.post(
        "/api/accounts",
        json={
            "label": "Joel Desk",
            "deposit": 1000,
            "password": "secret1",
            "avatar": tiny_png,
            "follow_auto": True,
        },
    )
    assert res.status_code == 200
    created = res.json()
    code = created["account"]["account_code"]
    token = created["token"]
    headers = {
        "X-JM-Account-Id": created["account"]["account_id"],
        "X-JM-Account-Token": token,
    }
    assert created["account"]["account_label"] == "Joel Desk"
    assert created["account"]["has_password"] is True
    assert created["account"]["avatar"].startswith("data:image/png")

    # Seed a closed trade directly on the account journal (history must survive).
    from app.api.deps import get_engine

    engine = get_engine()
    acct = engine.accounts.get_by_code(code)
    assert acct is not None
    acct.journal._trades.appendleft(
        TradeLog(
            ticket="hist-1",
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            entry=4100.0,
            exit=4110.0,
            status=TradeStatus.CLOSED,
            realized_pnl=10.0,
            close_reason="take_profit",
            strategy="Liquidity_Sweep_SMC",
            opened_at=utcnow(),
            closed_at=utcnow(),
        )
    )
    engine.accounts.save()

    login = await client.post(
        "/api/accounts/login",
        json={"code": code, "password": "secret1"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["account"]["account_code"] == code
    assert body["token"] == token
    assert body["trades"]["summary"]["total"] == 1
    assert body["trades"]["trades"][0]["realized_pnl"] == 10.0

    headers = {
        "X-JM-Account-Id": body["account"]["account_id"],
        "X-JM-Account-Token": body["token"],
    }
    patch = await client.patch(
        "/api/accounts/me",
        headers=headers,
        json={"label": "Joel Gold"},
    )
    assert patch.status_code == 200
    assert patch.json()["account"]["account_label"] == "Joel Gold"

    pwd = await client.post(
        "/api/accounts/me/password",
        headers=headers,
        json={"current_password": "secret1", "new_password": "secret2"},
    )
    assert pwd.status_code == 200

    bad = await client.post(
        "/api/accounts/login",
        json={"code": code, "password": "secret1"},
    )
    assert bad.status_code == 401

    ok = await client.post(
        "/api/accounts/login",
        json={"code": code, "password": "secret2"},
    )
    assert ok.status_code == 200
    assert ok.json()["trades"]["summary"]["total"] == 1
    assert ok.json()["account"]["account_label"] == "Joel Gold"

    lookup = await client.get(f"/api/accounts/lookup/{code}")
    assert lookup.status_code == 200
    assert lookup.json()["label"] == "Joel Gold"
    assert lookup.json()["has_password"] is True
