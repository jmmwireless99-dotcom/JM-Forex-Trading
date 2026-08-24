"""Daily P&L must reflect journal when broker positions are not restored."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine  # noqa: F401
from app.paper_accounts.registry import PaperAccountRegistry


def test_daily_pnl_from_journal_after_load(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "acc-1",
                    "code": "3295D7",
                    "label": "Client demo",
                    "token": "tok",
                    "follow_auto": True,
                    "is_desk": False,
                    "created_at": "2026-08-19T00:00:00+00:00",
                    "deposit": 1000.0,
                    "balance": 1143.24,
                    "trades": [
                        {
                            "id": "t1",
                            "symbol": "XAUUSD",
                            "side": "BUY",
                            "lots": 0.01,
                            "entry": 4484.03,
                            "status": "CLOSED",
                            "realized_pnl": 95.38,
                        },
                        {
                            "id": "t2",
                            "symbol": "XAUUSD",
                            "side": "SELL",
                            "lots": 0.01,
                            "entry": 4357.79,
                            "status": "CLOSED",
                            "realized_pnl": -62.36,
                        },
                        {
                            "id": "t3",
                            "symbol": "XAUUSD",
                            "side": "BUY",
                            "lots": 0.01,
                            "entry": 4357.58,
                            "status": "CLOSED",
                            "realized_pnl": 56.44,
                        },
                        {
                            "id": "t4",
                            "symbol": "XAUUSD",
                            "side": "BUY",
                            "lots": 0.01,
                            "entry": 4354.0,
                            "status": "CLOSED",
                            "realized_pnl": 53.78,
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    acc = reg.get("acc-1")
    assert acc is not None
    payload = acc.snapshot_payload()
    assert payload["daily_pnl"] == 143.24
    assert acc.broker.snapshot().daily_pnl == 0.0
