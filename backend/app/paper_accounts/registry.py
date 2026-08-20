"""Isolated paper demo accounts — each client has own capital + trade history."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.engine.trade_journal import TradeJournal
from app.models.domain import utcnow
from app.risk.manager import RiskManager

log = logging.getLogger(__name__)

DESK_LABEL = "Internal desk"


def _short_code() -> str:
    return secrets.token_hex(3).upper()  # 6 chars


def _contract_size(symbol: str) -> float:
    return PaperBroker.CONTRACT_SIZES.get(symbol.upper(), PaperBroker.DEFAULT_CONTRACT_SIZE)


def _pnl_at_price(
    *,
    entry: float,
    side: str,
    lots: float,
    symbol: str,
    price: float,
) -> float:
    from app.models.domain import Side

    direction = 1 if Side(side) == Side.BUY else -1
    move = (price - entry) * direction
    return round(move * lots * _contract_size(symbol), 2)


def _exit_from_pnl(
    *,
    entry: float,
    side: str,
    lots: float,
    symbol: str,
    pnl: float,
) -> float | None:
    if lots <= 0 or pnl == 0:
        return None
    from app.models.domain import Side

    direction = 1 if Side(side) == Side.BUY else -1
    move = pnl / (lots * _contract_size(symbol))
    return round(entry + move * direction, 2)


def _settle_open_trade_row(row: dict) -> dict:
    """Convert a persisted OPEN trade into a settled CLOSED row on restart."""
    unrealized = float(row.get("unrealized_pnl") or 0)
    realized = float(row.get("realized_pnl") or 0)
    pnl = realized if realized != 0 else unrealized
    exit_price = row.get("exit")
    entry = row.get("entry")
    if exit_price is None and entry is not None and pnl != 0:
        exit_price = _exit_from_pnl(
            entry=float(entry),
            side=row.get("side", "BUY"),
            lots=float(row.get("lots") or 0.01),
            symbol=row.get("symbol") or "XAUUSD",
            pnl=pnl,
        )
    settled = {
        **row,
        "status": "CLOSED",
        "close_reason": row.get("close_reason") or "session_restart",
        "realized_pnl": round(pnl, 2),
        "unrealized_pnl": 0.0,
        "exit": exit_price,
    }
    if not settled.get("closed_at"):
        settled["closed_at"] = utcnow().isoformat()
    return settled


@dataclass
class PaperAccount:
    """One client's paper book: capital, positions, and trade log."""

    id: str
    code: str
    label: str
    token: str
    broker: PaperBroker
    journal: TradeJournal
    risk: RiskManager
    follow_auto: bool = True
    is_desk: bool = False
    created_at: datetime = field(default_factory=utcnow)

    def public_info(self) -> dict:
        snap = self.broker.snapshot()
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "follow_auto": self.follow_auto,
            "created_at": self.created_at.isoformat(),
            "deposit": snap.deposit,
            "balance": snap.balance,
            "equity": snap.equity,
            "open_positions": snap.open_positions,
            "trades_logged": self.journal.summary().get("total", 0),
        }

    def snapshot_payload(self) -> dict:
        """Account snapshot dict tagged with identity for API / WS clients."""
        snap = self.broker.snapshot().model_dump(mode="json")
        return {
            **snap,
            "account_id": self.id,
            "account_code": self.code,
            "account_label": self.label,
            "follow_auto": self.follow_auto,
        }


class PaperAccountRegistry:
    """In-memory multi-account store with optional JSON persistence."""

    def __init__(self, settings: Settings, *, store_path: Path | None = None) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._accounts: dict[str, PaperAccount] = {}
        self._by_token: dict[str, str] = {}
        backend_data = Path(__file__).resolve().parents[1] / "data" / "paper_accounts.json"
        self.store_path = store_path or backend_data
        self._load()

    def _new_book(self, deposit: float) -> tuple[PaperBroker, TradeJournal, RiskManager]:
        broker = PaperBroker(deposit, self.settings.base_currency)
        journal = TradeJournal(maxlen=500)
        risk = RiskManager(self.settings)
        risk.reset_daily(deposit)
        return broker, journal, risk

    def ensure_desk(self, deposit: float | None = None) -> PaperAccount:
        """Reuse a single internal desk book (not shown to clients)."""
        with self._lock:
            for acc in self._accounts.values():
                if acc.is_desk or (acc.label == DESK_LABEL and not acc.follow_auto):
                    acc.is_desk = True
                    acc.follow_auto = False
                    return acc
        return self.create(
            deposit=deposit,
            label=DESK_LABEL,
            follow_auto=False,
            is_desk=True,
        )

    def create(
        self,
        *,
        deposit: float | None = None,
        label: str | None = None,
        follow_auto: bool = True,
        is_desk: bool = False,
    ) -> PaperAccount:
        amount = float(deposit if deposit is not None else self.settings.initial_balance)
        amount = max(50.0, min(amount, 1_000_000.0))
        broker, journal, risk = self._new_book(amount)
        acc = PaperAccount(
            id=str(uuid.uuid4()),
            code=_short_code(),
            label=(label or "").strip() or f"Demo {amount:,.0f}",
            token=secrets.token_urlsafe(24),
            broker=broker,
            journal=journal,
            risk=risk,
            follow_auto=follow_auto and not is_desk,
            is_desk=is_desk,
        )
        with self._lock:
            self._accounts[acc.id] = acc
            self._by_token[acc.token] = acc.id
            self._save()
        log.info(
            "paper account created id=%s code=%s deposit=%s desk=%s",
            acc.id,
            acc.code,
            amount,
            is_desk,
        )
        return acc

    def get(self, account_id: str) -> PaperAccount | None:
        with self._lock:
            return self._accounts.get(account_id)

    def get_by_token(self, token: str) -> PaperAccount | None:
        with self._lock:
            aid = self._by_token.get(token)
            return self._accounts.get(aid) if aid else None

    def require(self, account_id: str, token: str | None = None) -> PaperAccount:
        acc = self.get(account_id)
        if acc is None:
            raise KeyError("Account not found")
        if acc.is_desk:
            raise KeyError("Account not found")
        if token and acc.token != token:
            raise PermissionError("Invalid account token")
        return acc

    def list_public(self) -> list[dict]:
        with self._lock:
            return [a.public_info() for a in self._accounts.values() if not a.is_desk]

    def all(self) -> list[PaperAccount]:
        with self._lock:
            return list(self._accounts.values())

    def clients(self) -> list[PaperAccount]:
        with self._lock:
            return [a for a in self._accounts.values() if not a.is_desk]

    def auto_followers(self) -> list[PaperAccount]:
        with self._lock:
            return [a for a in self._accounts.values() if a.follow_auto and not a.is_desk]

    def save(self) -> None:
        with self._lock:
            self._save()

    def persist(self) -> None:
        self.save()

    def reconcile_session_restarts(self, mids: dict[str, float]) -> int:
        """Heal session_restart closes that were saved with $0 PnL (missing exit)."""
        from app.models.domain import TradeStatus

        fixed = 0
        with self._lock:
            for acc in self._accounts.values():
                if acc.is_desk:
                    continue
                account_fixed = False
                for row in acc.journal._trades:
                    if row.status != TradeStatus.CLOSED:
                        continue
                    if row.close_reason != "session_restart":
                        continue
                    if row.realized_pnl != 0 or row.exit is not None:
                        continue
                    if row.entry is None:
                        continue
                    opened = row.opened_at or row.closed_at
                    if opened is not None:
                        age_hours = (utcnow() - opened).total_seconds() / 3600.0
                        # Only heal fresh restart rows — skip archived history restores
                        if age_hours > 48:
                            continue
                    mid = mids.get(row.symbol)
                    if mid is None:
                        continue
                    pnl = _pnl_at_price(
                        entry=float(row.entry),
                        side=row.side.value,
                        lots=float(row.lots),
                        symbol=row.symbol,
                        price=mid,
                    )
                    row.realized_pnl = pnl
                    row.unrealized_pnl = 0.0
                    row.exit = round(mid, 2)
                    row.closed_at = row.closed_at or utcnow()
                    acc.broker.balance = round(acc.broker.balance + pnl, 2)
                    account_fixed = True
                    fixed += 1
                if account_fixed:
                    acc.risk.reset_daily(acc.broker.balance)
            if fixed:
                self._save()
        if fixed:
            log.info("reconciled %s session_restart trade(s) with market PnL", fixed)
        return fixed

    def _save(self) -> None:
        """Persist client account metadata + balances (desk excluded)."""
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = []
            for acc in self._accounts.values():
                if acc.is_desk:
                    continue
                snap = acc.broker.snapshot()
                payload.append(
                    {
                        "id": acc.id,
                        "code": acc.code,
                        "label": acc.label,
                        "token": acc.token,
                        "follow_auto": acc.follow_auto,
                        "is_desk": False,
                        "created_at": acc.created_at.isoformat(),
                        "deposit": snap.deposit,
                        "balance": snap.balance,
                        "trades": [
                            t.model_dump(mode="json")
                            for t in acc.journal.list(500, include_rejected=True)
                        ],
                    }
                )
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.store_path)
        except Exception:  # noqa: BLE001
            log.exception("failed to persist paper accounts")

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.exception("failed to load paper accounts")
            return
        if not isinstance(raw, list):
            return
        for row in raw:
            try:
                if row.get("is_desk"):
                    continue
                deposit = float(row.get("deposit") or self.settings.initial_balance)
                balance = float(row.get("balance") or deposit)
                broker, journal, risk = self._new_book(deposit)
                broker.balance = balance
                broker.deposit = deposit
                from app.models.domain import Side, TradeLog, TradeStatus

                raw_trades = row.get("trades") or []
                settled_rows: list[dict] = []
                restart_pnl = 0.0
                for t in raw_trades:
                    try:
                        status = TradeStatus(t.get("status", "CLOSED"))
                        if status == TradeStatus.OPEN:
                            t = _settle_open_trade_row(t)
                            restart_pnl += float(t.get("realized_pnl") or 0)
                            status = TradeStatus.CLOSED
                        settled_rows.append(t)
                    except Exception:  # noqa: BLE001
                        continue
                if restart_pnl:
                    broker.balance = round(broker.balance + restart_pnl, 2)
                for t in settled_rows:
                    try:
                        status = TradeStatus(t.get("status", "CLOSED"))
                        row_log = TradeLog(
                            id=t.get("id") or str(uuid.uuid4()),
                            ticket=t.get("ticket") or str(uuid.uuid4()),
                            symbol=t.get("symbol") or "XAUUSD",
                            side=Side(t.get("side", "BUY")),
                            lots=float(t.get("lots") or 0.01),
                            entry=t.get("entry"),
                            stop_loss=t.get("stop_loss"),
                            take_profit=t.get("take_profit"),
                            exit=t.get("exit"),
                            status=status,
                            strategy=t.get("strategy"),
                            comment=t.get("comment") or "",
                            close_reason=t.get("close_reason"),
                            unrealized_pnl=float(t.get("unrealized_pnl") or 0),
                            realized_pnl=float(t.get("realized_pnl") or 0),
                            mode=t.get("mode") or "paper",
                            reject_reason=t.get("reject_reason"),
                        )
                        journal._trades.append(row_log)
                        journal._by_ticket[row_log.ticket] = row_log
                    except Exception:  # noqa: BLE001
                        continue
                created = row.get("created_at")
                created_at = (
                    datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created
                    else utcnow()
                )
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                acc = PaperAccount(
                    id=row["id"],
                    code=row.get("code") or _short_code(),
                    label=row.get("label") or "Demo",
                    token=row.get("token") or secrets.token_urlsafe(24),
                    broker=broker,
                    journal=journal,
                    risk=risk,
                    follow_auto=bool(row.get("follow_auto", True)),
                    is_desk=False,
                    created_at=created_at,
                )
                self._accounts[acc.id] = acc
                self._by_token[acc.token] = acc.id
            except Exception:  # noqa: BLE001
                log.exception("skip corrupt paper account row")
        log.info("loaded %s paper accounts from %s", len(self._accounts), self.store_path)
