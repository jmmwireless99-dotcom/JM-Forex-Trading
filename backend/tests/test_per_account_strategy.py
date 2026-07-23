"""Per-account strategy preference isolates fills across clients."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import reset_engine
from app.core.config import Settings
from app.main import create_app
from app.paper_accounts.registry import PaperAccountRegistry


@pytest.fixture
async def client():
    reset_engine(Settings(tick_interval_seconds=0.05, auto_strategy=False))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = reset_engine(Settings())
    await engine.stop()


async def _acct(client, label):
    res = await client.post(
        "/api/accounts",
        json={"label": label, "deposit": 1000, "password": "secret1"},
    )
    assert res.status_code == 200
    body = res.json()
    return body, {
        "X-JM-Account-Id": body["account"]["account_id"],
        "X-JM-Account-Token": body["token"],
    }


@pytest.mark.asyncio
async def test_per_account_strategy_does_not_clobber_other(client):
    juan, h_juan = await _acct(client, "Juan")
    joel, h_joel = await _acct(client, "Joel")

    r1 = await client.post(
        "/api/account/strategy",
        headers=h_juan,
        json={"name": "EMA_RSI_Scalp"},
    )
    assert r1.status_code == 200
    assert r1.json()["strategy_pref"] == "EMA_RSI_Scalp"

    r2 = await client.post(
        "/api/account/strategy",
        headers=h_joel,
        json={"name": "London_Judas_Sweep"},
    )
    assert r2.status_code == 200
    assert r2.json()["strategy_pref"] == "London_Judas_Sweep"

    me_juan = await client.get("/api/account/strategy", headers=h_juan)
    me_joel = await client.get("/api/account/strategy", headers=h_joel)
    assert me_juan.json()["strategy_pref"] == "EMA_RSI_Scalp"
    assert me_joel.json()["strategy_pref"] == "London_Judas_Sweep"

    auto = await client.post(
        "/api/account/strategy",
        headers=h_juan,
        json={"name": "auto"},
    )
    assert auto.json()["strategy_pref"] == "auto"
    # Joel still locked
    me_joel2 = await client.get("/api/account/strategy", headers=h_joel)
    assert me_joel2.json()["strategy_pref"] == "London_Judas_Sweep"


def test_accepts_strategy_signal_matrix(tmp_path):
    settings = Settings()
    reg = PaperAccountRegistry(settings, store_path=tmp_path / "a.json")
    a = reg.create(label="A", deposit=1000)
    reg.set_strategy_pref(a, "EMA_RSI_Scalp")
    assert reg.accepts_strategy_signal(
        a,
        signal_strategy="EMA_RSI_Scalp",
        session_strategy="London_Judas_Sweep",
        allow_trading=True,
    )
    assert not reg.accepts_strategy_signal(
        a,
        signal_strategy="London_Judas_Sweep",
        session_strategy="London_Judas_Sweep",
        allow_trading=True,
    )

    reg.set_strategy_pref(a, "auto")
    assert reg.accepts_strategy_signal(
        a,
        signal_strategy="London_Judas_Sweep",
        session_strategy="London_Judas_Sweep",
        allow_trading=True,
    )
    assert not reg.accepts_strategy_signal(
        a,
        signal_strategy="EMA_RSI_Scalp",
        session_strategy="London_Judas_Sweep",
        allow_trading=True,
    )
    assert not reg.accepts_strategy_signal(
        a,
        signal_strategy="London_Judas_Sweep",
        session_strategy="London_Judas_Sweep",
        allow_trading=False,
    )
