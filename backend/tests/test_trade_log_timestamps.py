"""Persisted trade opened_at / closed_at must survive registry reload."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.paper_accounts.registry import PaperAccountRegistry


def _write_store(path: Path, *, trades: list[dict]) -> None:
    payload = [
        {
            "id": "acc-1",
            "code": "03BDC3",
            "label": "Demo",
            "token": "tok",
            "follow_auto": True,
            "is_desk": False,
            "created_at": "2026-08-20T02:15:05+00:00",
            "deposit": 1000.0,
            "balance": 1503.67,
            "trades": trades,
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_closed_trades_keep_stored_timestamps_on_load(tmp_path: Path) -> None:
    opened = "2026-08-20T06:30:00+00:00"
    closed = "2026-08-20T07:15:00+00:00"
    store = tmp_path / "paper_accounts.json"
    _write_store(
        store,
        trades=[
            {
                "id": "t1",
                "ticket": "pos-1",
                "symbol": "XAUUSD",
                "side": "BUY",
                "lots": 0.01,
                "entry": 2480.0,
                "exit": 2485.0,
                "status": "CLOSED",
                "realized_pnl": 5.0,
                "opened_at": opened,
                "closed_at": closed,
            }
        ],
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    row = acc.journal.list(10)[0]
    assert row.opened_at == datetime(2026, 8, 20, 6, 30, tzinfo=timezone.utc)
    assert row.closed_at == datetime(2026, 8, 20, 7, 15, tzinfo=timezone.utc)

    reg.save()
    reloaded = PaperAccountRegistry(Settings(), store_path=store)
    acc2 = reloaded.get("acc-1")
    assert acc2 is not None
    row2 = acc2.journal.list(10)[0]
    assert row2.opened_at == datetime(2026, 8, 20, 6, 30, tzinfo=timezone.utc)
    assert row2.closed_at == datetime(2026, 8, 20, 7, 15, tzinfo=timezone.utc)


def test_open_trade_settle_preserves_opened_at(tmp_path: Path) -> None:
    opened = "2026-08-25T14:00:00+00:00"
    store = tmp_path / "paper_accounts.json"
    _write_store(
        store,
        trades=[
            {
                "id": "t1",
                "ticket": "pos-1",
                "symbol": "XAUUSD",
                "side": "SELL",
                "lots": 0.01,
                "entry": 2500.0,
                "status": "OPEN",
                "unrealized_pnl": 10.0,
                "realized_pnl": 0.0,
                "opened_at": opened,
            }
        ],
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    row = acc.journal.list(10)[0]
    assert row.opened_at == datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
    assert row.closed_at == datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
