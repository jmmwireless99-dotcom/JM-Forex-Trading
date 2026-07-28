"""Paper strategy lab — tiny lots, single book, Judas off auto."""

import asyncio
from datetime import datetime, timezone

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import Side, Signal, Tick
from app.risk.manager import RiskManager
from app.strategies.session import SESSION_STRATEGY, next_session_hint


def test_paper_lab_defaults():
    s = Settings()
    assert s.paper_test_mode is True
    assert s.lots_per_1000 == 0.02
    assert s.max_open_positions == 1


def test_london_auto_uses_ema_not_judas():
    assert SESSION_STRATEGY["london"] == "EMA_RSI_Scalp"
    nxt = next_session_hint(datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc))
    assert nxt["strategy"] == "EMA_RSI_Scalp"


def test_lots_for_balance_paper_lab():
    risk = RiskManager(Settings(lots_per_1000=0.02))
    assert risk.lots_for_balance(1000) == 0.02
    assert risk.lots_for_balance(5000) == 0.1


def test_paper_lab_single_book_targets(monkeypatch):
    engine = TradingEngine(
        Settings(
            paper_test_mode=True,
            paper_test_single_book=True,
            auto_strategy=False,
            tick_interval_seconds=0.05,
        )
    )
    engine.accounts.create(label="Demo A", deposit=1000, follow_auto=True)
    engine.accounts.create(label="Demo B", deposit=1000, follow_auto=True)

    captured: list[str] = []

    async def fake_for_account(
        signal, tick, *, account, signal_db_id=None, london_signal_id=None
    ):
        captured.append(account.id)

    monkeypatch.setattr(engine, "_handle_signal_for_account", fake_for_account)

    sig = Signal(
        symbol="XAUUSD",
        side=Side.BUY,
        strategy="EMA_RSI_Scalp",
        reason="test",
        strength=0.9,
    )
    tick = Tick(symbol="XAUUSD", bid=4000.0, ask=4000.2, mid=4000.1)
    asyncio.run(engine._handle_signal(sig, tick))
    assert len(captured) == 1
