"""Trade log timestamps must survive JSON load/save cycles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine  # noqa: F401
from app.paper_accounts.registry import PaperAccountRegistry


def test_load_preserves_opened_and_closed_at(tmp_path: Path) -> None:
    opened = "2026-08-19T03:20:01+00:00"
    closed = "2026-08-19T03:40:00+00:00"
    store = tmp_path / "paper_accounts.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "acc-1",
                    "code": "ABC123",
                    "label": "Demo",
                    "token": "tok",
                    "follow_auto": True,
                    "is_desk": False,
                    "created_at": "2026-08-19T00:00:00+00:00",
                    "deposit": 1000.0,
                    "balance": 1050.0,
                    "trades": [
                        {
                            "id": "t1",
                            "ticket": "pos-1",
                            "symbol": "XAUUSD",
                            "side": "BUY",
                            "lots": 0.01,
                            "entry": 4354.0,
                            "status": "CLOSED",
                            "strategy": "AI_ML/EMA_RSI_Scalp",
                            "realized_pnl": 53.78,
                            "opened_at": opened,
                            "closed_at": closed,
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
    assert row.opened_at == datetime(2026, 8, 19, 3, 20, 1, tzinfo=timezone.utc)
    assert row.closed_at == datetime(2026, 8, 19, 3, 40, tzinfo= timezone.utc)
