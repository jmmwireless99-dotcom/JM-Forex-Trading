"""Paper desk login by account code + password."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine  # noqa: F401
from app.investment.users import hash_password
from app.paper_accounts.registry import PaperAccountRegistry


def test_authenticate_by_code(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "acc-1",
                    "code": "3295D7",
                    "label": "Client demo",
                    "token": "secret-token",
                    "follow_auto": True,
                    "is_desk": False,
                    "created_at": "2026-08-19T00:00:00+00:00",
                    "deposit": 1000.0,
                    "balance": 1143.24,
                    "password_hash": hash_password("demo12345"),
                    "trades": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    reg = PaperAccountRegistry(Settings(), store_path=store)
    assert reg.authenticate_by_code("3295D7", "demo12345") is not None
    assert reg.authenticate_by_code("3295D7", "wrong") is None
    assert reg.authenticate_by_code("NOPE", "demo12345") is None
