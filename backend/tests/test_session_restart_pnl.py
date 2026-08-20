"""Session restart must preserve open-trade PnL across deploys."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine  # noqa: F401 — init app package
from app.models.domain import Side, TradeStatus
from app.paper_accounts.registry import PaperAccountRegistry


def _write_store(path: Path, *, balance: float, trades: list[dict]) -> None:
    payload = [
        {
            "id": "acc-1",
            "code": "ABC123",
            "label": "Demo",
            "token": "tok",
            "follow_auto": True,
            "is_desk": False,
            "created_at": "2026-08-20T02:15:05+00:00",
            "deposit": 1000.0,
            "balance": balance,
            "trades": trades,
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_open_trade_settles_with_saved_unrealized_pnl(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    _write_store(
        store,
        balance=1000.0,
        trades=[
            {
                "id": "t1",
                "ticket": "pos-1",
                "symbol": "XAUUSD",
                "side": "BUY",
                "lots": 0.01,
                "entry": 4484.03,
                "stop_loss": 4472.49,
                "take_profit": 4512.87,
                "status": "OPEN",
                "strategy": "AI_ML/EMA_VWAP_Scalp",
                "unrealized_pnl": 18.42,
                "realized_pnl": 0.0,
            }
        ],
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    closed = acc.journal.list(10)[0]
    assert closed.status == TradeStatus.CLOSED
    assert closed.close_reason == "session_restart"
    assert closed.realized_pnl == 18.42
    assert closed.exit == pytest.approx(4502.45, abs=0.02)
    assert acc.broker.balance == pytest.approx(1018.42, abs=0.01)


def test_reconcile_heals_zero_pnl_session_restart(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    _write_store(
        store,
        balance=1000.0,
        trades=[
            {
                "id": "t1",
                "ticket": "pos-1",
                "symbol": "XAUUSD",
                "side": "BUY",
                "lots": 0.01,
                "entry": 4484.03,
                "status": "CLOSED",
                "close_reason": "session_restart",
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "exit": None,
                "strategy": "AI_ML/EMA_VWAP_Scalp",
            }
        ],
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    fixed = reg.reconcile_session_restarts({"XAUUSD": 4500.0})
    assert fixed == 1
    row = acc.journal.list(10)[0]
    assert row.realized_pnl == pytest.approx(15.97, abs=0.02)
    assert row.exit == 4500.0
    assert acc.broker.balance == pytest.approx(1015.97, abs=0.02)


def test_reconcile_skips_already_settled_trades(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    _write_store(
        store,
        balance=1018.42,
        trades=[
            {
                "id": "t1",
                "ticket": "pos-1",
                "symbol": "XAUUSD",
                "side": Side.BUY.value,
                "lots": 0.01,
                "entry": 4484.03,
                "status": "CLOSED",
                "close_reason": "session_restart",
                "realized_pnl": 18.42,
                "exit": 4502.45,
            }
        ],
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    assert reg.reconcile_session_restarts({"XAUUSD": 4500.0}) == 0
