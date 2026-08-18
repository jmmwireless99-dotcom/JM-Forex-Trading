from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import reset_engine
from app.core.config import Settings, get_settings
from app.engine.trading_engine import TradingEngine
from app.paper_accounts.registry import PaperAccountRegistry


@pytest.mark.asyncio
async def test_auto_fill_targets_single_book(tmp_path):
    get_settings.cache_clear()
    settings = Settings(
        auto_strategy=False,
        default_strategy="manual_only",
        news_filter=False,
        auto_fill_single_book=True,
        auto_fill_account_code="",
    )
    engine = TradingEngine(settings)
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")
    engine._desk = engine.accounts.ensure_desk(settings.initial_balance)

    base = datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)
    a1 = engine.accounts.create(label="First", follow_auto=True)
    a1.created_at = base
    a2 = engine.accounts.create(label="Second", follow_auto=True)
    a2.created_at = base + timedelta(minutes=1)
    a3 = engine.accounts.create(label="Manual", follow_auto=False)
    a3.created_at = base + timedelta(minutes=2)
    assert a3.follow_auto is False

    targets = engine._auto_fill_targets()
    assert len(targets) == 1
    assert targets[0].id == a1.id

    # connected session wins over earliest when single-book
    engine.register_connected_account(a2)
    connected = engine._auto_fill_targets()
    assert len(connected) == 1
    assert connected[0].id == a2.id
    engine.unregister_connected_account(a2.id)
    assert engine._auto_fill_targets()[0].id == a1.id

    # pinned code wins over earliest
    engine.settings = settings.model_copy(update={"auto_fill_account_code": a2.code})
    pinned = engine._auto_fill_targets()
    assert len(pinned) == 1
    assert pinned[0].id == a2.id

    # fan-out mode: all auto followers (default / centralized desk)
    engine.settings = settings.model_copy(
        update={"auto_fill_single_book": False, "auto_fill_account_code": ""}
    )
    all_followers = engine._auto_fill_targets()
    assert {a.id for a in all_followers} == {a1.id, a2.id}

    await engine.stop()
    reset_engine(Settings())
    get_settings.cache_clear()
