"""Tests for MT4 real (live) account bridge linking."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.brokers.mt4_bridge import MT4FileBridge
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import OrderRequest, Side
from app.paper_accounts.registry import PaperAccountRegistry


@pytest.fixture
def mt4_real_engine(tmp_path: Path):
    bridge_dir = tmp_path / "mt4_real_bridge"
    bridge_dir.mkdir()
    (bridge_dir / "jm_status.csv").write_text("ok,5000.00,5012.50,0,2026-08-28 12:00:00\n")
    (bridge_dir / "jm_ticks.csv").write_text("XAUUSD,4591.36,4591.66,2026-08-28 12:00:00\n")

    store = tmp_path / "paper_accounts.json"
    settings = Settings(
        execution_mode="paper",
        mt4_real_bridge_dir=str(bridge_dir),
        mt4_real_account_code="REALFX",
        mt4_real_login="87654321",
        mt4_symbol="XAUUSD",
    )
    reg = PaperAccountRegistry(settings, store_path=store)
    acct = reg.create(deposit=5000.0, label="XM MT4 Real", follow_auto=False)
    acct.code = "REALFX"
    reg.save()

    engine = TradingEngine(settings)
    engine.accounts = reg
    engine.mt4_real = MT4FileBridge(bridge_dir, symbol="XAUUSD", desk_symbol="XAUUSD")
    return engine, acct


def test_mt4_real_account_shows_live_balance(mt4_real_engine):
    engine, acct = mt4_real_engine
    snap = engine.account_snapshot(acct)
    assert snap.balance == 5000.0
    assert snap.equity == 5012.50
    assert snap.paper is False

    payload = engine.account_payload(acct)
    assert payload["account_code"] == "REALFX"
    assert payload["mt4_real"] is True
    assert payload["account_kind"] == "real"
    assert payload["mt_platform"] == "mt4_real"
    assert payload["mt4_real_login"] == "87654321"


def test_mt4_real_link_status(mt4_real_engine):
    engine, acct = mt4_real_engine
    status = engine.mt_demo_link_status(acct)
    assert status["linked"] is True
    assert status["platform"] == "mt4_real"
    assert status["account_kind"] == "real"
    assert status["mt4_real"] is True
    assert status["bridge_online"] is True


def test_mt4_real_not_in_auto_fill_by_default(mt4_real_engine):
    engine, acct = mt4_real_engine
    assert acct.follow_auto is False
    other = engine.accounts.create(deposit=500.0, label="Paper follower", follow_auto=True)
    targets = engine._auto_fill_targets()
    ids = {a.id for a in targets}
    assert other.id in ids
    assert acct.id not in ids


@pytest.mark.asyncio
async def test_mt4_real_rejects_paper_deposit(mt4_real_engine):
    engine, acct = mt4_real_engine
    with pytest.raises(ValueError, match="MT4 REAL-only"):
        await engine.set_paper_deposit(2000.0, account=acct)


@pytest.mark.asyncio
async def test_mt4_real_manual_order_uses_real_bridge(mt4_real_engine):
    engine, acct = mt4_real_engine

    saved_cmd: list[str] = []

    def fake_ea():
        import time

        for _ in range(40):
            if engine.mt4_real.command_file.exists():
                text = engine.mt4_real.command_file.read_text()
                if "OPEN" in text and "XAUUSD" in text:
                    saved_cmd.append(text)
                    cmd_id = text.strip().splitlines()[-1].split(",")[0]
                    engine.mt4_real.ack_file.write_text(f"{cmd_id},OK,777\n")
                    return
            time.sleep(0.05)

    import threading

    t = threading.Thread(target=fake_ea, daemon=True)
    t.start()
    order = await engine.manual_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            stop_loss=4580.0,
            take_profit=4610.0,
            comment="mt4-real",
        ),
        account=acct,
    )
    t.join(timeout=3)
    assert saved_cmd
    assert "XAUUSD" in saved_cmd[0]
    assert order.status.value == "FILLED"
