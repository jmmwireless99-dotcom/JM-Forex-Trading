"""Tests for MT5 demo account (DDDC3D) bridge linking."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.brokers.mt4_bridge import MT4FileBridge
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.paper_accounts.registry import PaperAccountRegistry


@pytest.fixture
def mt5_engine(tmp_path: Path):
    bridge_dir = tmp_path / "bridge"
    bridge_dir.mkdir()
    (bridge_dir / "jm_status.csv").write_text("ok,1000.00,1005.50,0,2026-08-28 12:00:00\n")
    (bridge_dir / "jm_ticks.csv").write_text("GOLD#,4591.36,4591.66,2026-08-28 12:00:00\n")

    store = tmp_path / "paper_accounts.json"
    settings = Settings(
        execution_mode="paper",
        mt5_bridge_dir=str(bridge_dir),
        mt_remote_bridge=True,
        mt5_demo_account_code="DDDC3D",
        mt5_demo_login="169250320",
        mt_symbol="GOLD#",
    )
    reg = PaperAccountRegistry(settings, store_path=store)
    acct = reg.create(deposit=994.36, label="XM MT5 Demo", follow_auto=False)
    acct.code = "DDDC3D"
    reg.save()

    engine = TradingEngine(settings)
    engine.accounts = reg
    engine.mt = MT4FileBridge(bridge_dir, symbol="GOLD#", desk_symbol="XAUUSD")
    return engine, acct


def test_mt_demo_account_shows_live_mt5_balance(mt5_engine):
    engine, acct = mt5_engine
    snap = engine.account_snapshot(acct)
    assert snap.balance == 1000.0
    assert snap.equity == 1005.50
    assert snap.paper is False

    payload = engine.account_payload(acct)
    assert payload["account_code"] == "DDDC3D"
    assert payload["mt5_linked"] is True
    assert payload["mt5_login"] == "169250320"
    assert payload["balance"] == 1000.0


def test_mt_demo_link_status(mt5_engine):
    engine, acct = mt5_engine
    status = engine.mt_demo_link_status(acct)
    assert status["linked"] is True
    assert status["bridge_online"] is True
    assert status["live_balance"] is True
    assert status["tick_ok"] is True
    assert status["mt5_login"] == "169250320"


def test_other_accounts_stay_paper(mt5_engine):
    engine, _ = mt5_engine
    other = engine.accounts.create(deposit=500.0, label="Other", follow_auto=True)
    snap = engine.account_snapshot(other)
    assert snap.balance == 500.0
    assert snap.paper is True
