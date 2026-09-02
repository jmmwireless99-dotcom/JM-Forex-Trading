"""Paper lot clamp heals corrupt restore rows."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.paper_accounts.registry import (
    MAX_PAPER_LOTS,
    PaperAccountRegistry,
    _sanitize_trade_lots,
)


def test_sanitize_clamps_lots_and_rescales_pnl():
    row = {
        "ticket": "t-bad",
        "lots": 4.99,
        "realized_pnl": -3188.0,
        "unrealized_pnl": 0.0,
    }
    fixed = _sanitize_trade_lots(row)
    assert fixed["lots"] == MAX_PAPER_LOTS
    assert fixed["realized_pnl"] == round(-3188.0 * (MAX_PAPER_LOTS / 4.99), 2)


def test_registry_load_heals_corrupt_lots(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "acc-1",
                    "code": "5335D2",
                    "label": "Demo",
                    "token": "tok",
                    "follow_auto": True,
                    "is_desk": False,
                    "created_at": "2026-09-01T12:00:00+00:00",
                    "deposit": 1000.0,
                    "balance": -6400.0,
                    "trades": [
                        {
                            "id": "t1",
                            "ticket": "pos-1",
                            "symbol": "XAUUSD",
                            "side": "SELL",
                            "lots": 4.99,
                            "entry": 4087.0,
                            "exit": 4093.0,
                            "status": "CLOSED",
                            "close_reason": "stop_loss",
                            "realized_pnl": -3188.0,
                            "strategy": "London_Judas_Sweep",
                            "opened_at": "2026-09-01T12:01:13+00:00",
                            "closed_at": "2026-09-01T12:01:13+00:00",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    row = acc.journal.list(10)[0]
    assert row.lots == MAX_PAPER_LOTS
    assert row.realized_pnl == round(-3188.0 * (MAX_PAPER_LOTS / 4.99), 2)
    assert acc.broker.balance == round(1000.0 + row.realized_pnl, 2)
