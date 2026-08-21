from __future__ import annotations

import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.auto_config import AutoConfig
from app.broker import LabBroker
from app.pair_strategies import preset_for

log = logging.getLogger(__name__)

SUITE_LABEL_PREFIX = "Pair suite · "
PAIR_SUITE_SYMBOLS = ("EURUSD", "GBPUSD", "AUDNZD", "EURCHF", "XAUUSD")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LabAccount:
    account_id: str
    code: str
    token: str
    label: str
    broker: LabBroker
    auto: AutoConfig = field(default_factory=AutoConfig)
    created_at: str = field(default_factory=lambda: _now().isoformat())

    def snapshot(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "code": self.code,
            "label": self.label,
            "currency": self.broker.currency,
            "deposit": self.broker.deposit,
            "balance": self.broker.balance,
            "equity": self.broker.equity(),
            "daily_pnl": self.broker.daily_pnl(),
            "open_positions": len(self.broker.open_positions()),
            "paper": True,
            "auto": self.auto.to_dict(),
        }


class LabAccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._accounts: dict[str, LabAccount] = {}
        self._by_token: dict[str, str] = {}
        self._by_code: dict[str, str] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _gen_code(self) -> str:
        for _ in range(50):
            code = secrets.token_hex(3).upper()
            if code not in self._by_code:
                return code
        return secrets.token_hex(4).upper()

    def create(self, *, deposit: float = 10_000.0, label: str = "Lab demo") -> LabAccount:
        with self._lock:
            aid = str(uuid.uuid4())
            token = secrets.token_urlsafe(24)
            code = self._gen_code()
            acc = LabAccount(
                account_id=aid,
                code=code,
                token=token,
                label=label[:80],
                broker=LabBroker(deposit=deposit),
            )
            self._accounts[aid] = acc
            self._by_token[token] = aid
            self._by_code[code] = aid
            self.persist()
            return acc

    def get(self, account_id: str) -> LabAccount | None:
        return self._accounts.get(account_id)

    def auth(self, account_id: str, token: str | None) -> LabAccount:
        acc = self._accounts.get(account_id)
        if acc is None or not token or acc.token != token:
            raise PermissionError("Invalid lab account session")
        return acc

    def all_accounts(self) -> list[LabAccount]:
        return list(self._accounts.values())

    def find_suite_account(self, symbol: str) -> LabAccount | None:
        label = f"{SUITE_LABEL_PREFIX}{symbol.upper()}"
        for acc in self._accounts.values():
            if acc.label == label:
                return acc
        return None

    def bootstrap_pair_suite(
        self,
        *,
        deposit: float = 10_000.0,
        start_auto: bool = True,
    ) -> list[dict[str, Any]]:
        """Create one paper account per major pair for parallel dry-run testing."""
        rows: list[dict[str, Any]] = []
        for sym in PAIR_SUITE_SYMBOLS:
            acc = self.find_suite_account(sym)
            if acc is None:
                acc = self.create(deposit=deposit, label=f"{SUITE_LABEL_PREFIX}{sym}")
            preset = preset_for(sym)
            acc.auto.symbol = sym
            acc.auto.strategy = preset["strategy"]
            acc.auto.lots = float(preset["lots"])
            acc.auto.sl_pips = float(preset["sl_pips"])
            acc.auto.tp_pips = float(preset["tp_pips"])
            if start_auto:
                acc.auto.enabled = True
                acc.auto.last_bar_time = 0
                acc.auto.last_loss_bar_time = 0
                acc.auto.last_block_reason = None
            rows.append(
                {
                    "symbol": sym,
                    "account_id": acc.account_id,
                    "code": acc.code,
                    "token": acc.token,
                    "label": acc.label,
                    "strategy": acc.auto.strategy,
                    "auto_enabled": acc.auto.enabled,
                    "deposit": acc.broker.deposit,
                }
            )
        self.persist()
        return rows

    def persist(self) -> None:
        rows = []
        for acc in self._accounts.values():
            rows.append(
                {
                    "account_id": acc.account_id,
                    "code": acc.code,
                    "token": acc.token,
                    "label": acc.label,
                    "created_at": acc.created_at,
                    "broker": acc.broker.to_dict(),
                    "auto": acc.auto.to_dict(),
                }
            )
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("lab accounts load failed")
            return
        for row in rows:
            try:
                broker = LabBroker.from_dict(row.get("broker") or {})
                acc = LabAccount(
                    account_id=row["account_id"],
                    code=row["code"],
                    token=row["token"],
                    label=row.get("label") or "Lab demo",
                    broker=broker,
                    auto=AutoConfig.from_dict(row.get("auto")),
                    created_at=row.get("created_at") or _now().isoformat(),
                )
                self._accounts[acc.account_id] = acc
                self._by_token[acc.token] = acc.account_id
                self._by_code[acc.code] = acc.account_id
            except Exception:
                log.exception("skip corrupt lab account")
        log.info("loaded %s lab accounts", len(self._accounts))
