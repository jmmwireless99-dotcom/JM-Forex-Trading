"""Repair trade timestamps from ML history JSONL."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.trade_log_repair import repair_trade_timestamps


@pytest.fixture()
def ml_history(tmp_path: Path) -> Path:
    path = tmp_path / "ai_trade_history.jsonl"
    rows = [
        {
            "event": "open",
            "ticket": "tk-open",
            "opened_at": "2026-08-20T10:00:00+00:00",
            "closed_at": None,
        },
        {
            "event": "labeled",
            "ticket": "tk-labeled",
            "opened_at": "2026-08-21T08:30:00+00:00",
            "closed_at": "2026-08-21T09:15:00+00:00",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_repair_from_ml_history(tmp_path: Path, ml_history: Path) -> None:
    target = tmp_path / "paper_accounts.json"
    target.write_text(
        json.dumps(
            [
                {
                    "id": "a1",
                    "code": "ABC",
                    "token": "t",
                    "follow_auto": True,
                    "is_desk": False,
                    "deposit": 1000,
                    "balance": 1000,
                    "trades": [
                        {
                            "ticket": "tk-open",
                            "symbol": "XAUUSD",
                            "side": "BUY",
                            "status": "OPEN",
                            "opened_at": "2026-08-27T10:59:25Z",
                        },
                        {
                            "ticket": "tk-labeled",
                            "symbol": "XAUUSD",
                            "side": "SELL",
                            "status": "CLOSED",
                            "opened_at": "2026-08-27T10:59:25Z",
                            "closed_at": None,
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = repair_trade_timestamps(target=target, ml_history=ml_history)
    assert result["restored_trades"] == 2
    data = json.loads(target.read_text(encoding="utf-8"))
    trades = {t["ticket"]: t for t in data[0]["trades"]}
    assert trades["tk-open"]["opened_at"] == "2026-08-20T10:00:00+00:00"
    assert trades["tk-labeled"]["opened_at"] == "2026-08-21T08:30:00+00:00"
    assert trades["tk-labeled"]["closed_at"] == "2026-08-21T09:15:00+00:00"
