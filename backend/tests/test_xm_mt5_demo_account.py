"""Create XM MT5 demo JM FX account."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.engine.trading_engine import TradingEngine
from app.paper_accounts.registry import PaperAccountRegistry


def test_create_xm_mt5_demo_account(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acct = reg.create(deposit=1000, label="XM MT5 Demo", follow_auto=False)
    assert acct.code
    assert acct.token
    assert acct.label == "XM MT5 Demo"
    assert acct.follow_auto is False


def test_mt_demo_account_routing(tmp_path: Path) -> None:
    get_settings.cache_clear()
    settings = Settings(
        execution_mode="mt5",
        mt5_demo_account_code="",
        mt5_bridge_dir="",
    )
    engine = TradingEngine(settings)
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")
    engine._desk = engine.accounts.ensure_desk(settings.initial_balance)
    acct = engine.accounts.create(label="XM MT5 Demo", follow_auto=False)
    engine.settings.mt5_demo_account_code = acct.code
    assert engine._mt_demo_account().id == acct.id
