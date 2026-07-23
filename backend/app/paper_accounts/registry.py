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
from app.models.domain import utcnow
from app.paper_accounts.avatar import normalize_avatar
from app.paper_accounts.security import hash_password, verify_password
from app.risk.manager import RiskManager

log = logging.getLogger(__name__)

DESK_LABEL = "Internal desk"


def _short_code() -> str:
    return secrets.token_hex(3).upper()  # 6 chars


def normalize_mt5_login(raw: str | None) -> str:
    """MT5 login numbers are digits — used as JM FX username."""
    s = str(raw or "").strip()
    if not s:
        raise ValueError("MT5 account is required")
    if not s.isdigit() or not (5 <= len(s) <= 16):
        raise ValueError("MT5 account must be 5–16 digits (e.g. 25817283)")
    return s


def normalize_email(raw: str | None) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        raise ValueError("Gmail / email is required")
    if "@" not in s or "." not in s.split("@")[-1] or len(s) > 120:
        raise ValueError("Enter a valid email (e.g. name@gmail.com)")
    return s


def normalize_person_name(raw: str | None, *, field: str) -> str:
    s = " ".join(str(raw or "").strip().split())
    if not s:
        raise ValueError(f"{field} is required")
    if len(s) > 64:
        raise ValueError(f"{field} is too long")
    return s


@dataclass
class PaperAccount:
    """One client's paper book: capital, positions, and trade log."""

    id: str
    code: str
    label: str
    token: str
    broker: PaperBroker
    journal: object  # TradeJournal — typed loosely to avoid import cycles
    risk: RiskManager
    follow_auto: bool = True
    is_desk: bool = False
    created_at: datetime = field(default_factory=utcnow)
    password_hash: str | None = None
    avatar: str | None = None  # data-URL logo
    # When set, strategy auto-fills (incl. London Judas) use this lot size exactly.
    fixed_lots: float | None = None
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    mt5_login: str = ""  # same as code for client MT5-linked accounts

    def profile_public(self) -> dict:
        """Safe profile fields (no token / password)."""
        return {
            "account_id": self.id,
            "account_code": self.code,
            "account_label": self.label,
            "avatar": self.avatar or None,
            "has_password": bool(self.password_hash),
            "follow_auto": self.follow_auto,
            "fixed_lots": self.fixed_lots,
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "email": self.email or "",
            "mt5_login": self.mt5_login or "",
            "created_at": self.created_at.isoformat(),
        }

    def public_info(self) -> dict:
        snap = self.broker.snapshot()
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "avatar": self.avatar or None,
            "has_password": bool(self.password_hash),
            "follow_auto": self.follow_auto,
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "email": self.email or "",
            "mt5_login": self.mt5_login or "",
            "created_at": self.created_at.isoformat(),
            "deposit": snap.deposit,
            "balance": snap.balance,
            "equity": snap.equity,
            "open_positions": snap.open_positions,
            "trades_logged": self.journal.summary().get("total", 0),
            "fixed_lots": self.fixed_lots,
        }

    def snapshot_payload(self) -> dict:
        """Account snapshot dict tagged with identity for API / WS clients."""
        snap = self.broker.snapshot().model_dump(mode="json")
        return {
            **snap,
            **self.profile_public(),
        }


class PaperAccountRegistry:
    """In-memory multi-account store with optional JSON persistence."""

    def __init__(self, settings: Settings, *, store_path: Path | None = None) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._accounts: dict[str, PaperAccount] = {}
        self._by_token: dict[str, str] = {}
        self._by_code: dict[str, str] = {}
        backend_data = Path(__file__).resolve().parents[1] / "data" / "paper_accounts.json"
        self.store_path = store_path or backend_data
        self._load()

    def _new_book(self, deposit: float) -> tuple:
        from app.engine.trade_journal import TradeJournal

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
        password: str | None = None,
        avatar: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        mt5_login: str | None = None,
    ) -> PaperAccount:
        amount = float(deposit if deposit is not None else self.settings.initial_balance)
        amount = max(50.0, min(amount, 1_000_000.0))
        broker, journal, risk = self._new_book(amount)
        pwd_hash = None
        if password is not None and str(password).strip():
            pwd_hash = hash_password(str(password))
        logo = None
        if avatar is not None:
            logo = normalize_avatar(avatar) or None

        fn = ln = mail = mt5 = ""
        code = _short_code()
        mt5_raw = str(mt5_login).strip() if mt5_login is not None else ""
        if not is_desk and mt5_raw:
            # Client accounts linked to an MT5 login number.
            fn = normalize_person_name(first_name, field="First name")
            ln = normalize_person_name(last_name, field="Last name")
            mail = normalize_email(email)
            mt5 = normalize_mt5_login(mt5_raw)
            code = mt5
            if not pwd_hash:
                raise ValueError("MT5 password is required (min 6 characters)")
            with self._lock:
                if mt5.upper() in self._by_code:
                    raise ValueError("This MT5 account is already registered")
                for acc in self._accounts.values():
                    if (acc.email or "").lower() == mail:
                        raise ValueError("This email is already registered")

        display = (label or "").strip()
        if not display and (fn or ln):
            display = f"{fn} {ln}".strip()
        if not display:
            display = f"Demo {amount:,.0f}"

        acc = PaperAccount(
            id=str(uuid.uuid4()),
            code=code,
            label=display[:64],
            token=secrets.token_urlsafe(24),
            broker=broker,
            journal=journal,
            risk=risk,
            follow_auto=follow_auto and not is_desk,
            is_desk=is_desk,
            password_hash=pwd_hash,
            avatar=logo,
            first_name=fn,
            last_name=ln,
            email=mail,
            mt5_login=mt5,
        )
        with self._lock:
            if acc.code.upper() in self._by_code:
                raise ValueError("This MT5 account is already registered")
            self._accounts[acc.id] = acc
            self._by_token[acc.token] = acc.id
            self._by_code[acc.code.upper()] = acc.id
            self._save()
        log.info(
            "paper account created id=%s code=%s deposit=%s desk=%s has_password=%s mt5=%s",
            acc.id,
            acc.code,
            amount,
            is_desk,
            bool(pwd_hash),
            bool(mt5),
        )
        return acc

    def get(self, account_id: str) -> PaperAccount | None:
        with self._lock:
            return self._accounts.get(account_id)

    @staticmethod
    def _restore_mt5_login(row: dict) -> str:
        """Restore explicit MT5 link only — never treat random paper codes as MT5."""
        raw = str(row.get("mt5_login") or "").strip()
        if raw.isdigit() and 5 <= len(raw) <= 16:
            return raw
        code = str(row.get("code") or "").strip()
        # Legacy MT5 registrations always stored email + digit username as code.
        if (
            code.isdigit()
            and 5 <= len(code) <= 16
            and str(row.get("email") or "").strip()
            and str(row.get("first_name") or "").strip()
        ):
            return code
        return ""

    def get_by_token(self, token: str) -> PaperAccount | None:
        with self._lock:
            aid = self._by_token.get(token)
            return self._accounts.get(aid) if aid else None

    def get_by_code(self, code: str) -> PaperAccount | None:
        with self._lock:
            aid = self._by_code.get((code or "").strip().upper())
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

    def authenticate(self, code: str, password: str) -> PaperAccount:
        """Login with MT5 account (or legacy code) + password. Never clears history."""
        key = (code or "").strip()
        acc = self.get_by_code(key)
        if acc is None or acc.is_desk:
            raise KeyError("Invalid account or password")
        if not acc.password_hash:
            raise PermissionError(
                "This account has no password yet. Open the desk on the device "
                "that still has the session, then set a password in Profile."
            )
        if not verify_password(password, acc.password_hash):
            raise PermissionError("Invalid account or password")
        return acc

    def update_profile(
        self,
        account: PaperAccount,
        *,
        label: str | None = None,
        avatar: str | None = ...,  # type: ignore[assignment]
    ) -> PaperAccount:
        """Update label/logo only — balances and trade journal are untouched."""
        with self._lock:
            if label is not None:
                cleaned = label.strip()
                if cleaned:
                    account.label = cleaned[:64]
            if avatar is not ...:
                if avatar is None or str(avatar).strip() == "":
                    account.avatar = None
                else:
                    account.avatar = normalize_avatar(str(avatar)) or None
            self._save()
        return account

    def set_password(
        self,
        account: PaperAccount,
        *,
        new_password: str,
        current_password: str | None = None,
    ) -> PaperAccount:
        """Set or change password. Does not touch trades or capital."""
        with self._lock:
            if account.password_hash:
                if not current_password or not verify_password(
                    current_password, account.password_hash
                ):
                    raise PermissionError("Current password is incorrect")
            account.password_hash = hash_password(new_password)
            self._save()
        return account

    def rotate_token(self, account: PaperAccount) -> str:
        """Issue a fresh session token (logout-other-devices). Keeps history."""
        with self._lock:
            old = account.token
            self._by_token.pop(old, None)
            account.token = secrets.token_urlsafe(24)
            self._by_token[account.token] = account.id
            self._save()
            return account.token

    def set_fixed_lots(self, account: PaperAccount, lots: float | None) -> PaperAccount:
        """Set manual lot size for strategy fills. Does not touch trade history."""
        with self._lock:
            if lots is None:
                account.fixed_lots = None
            else:
                value = float(lots)
                if value < 0.01 or value > 10:
                    raise ValueError("Lots must be between 0.01 and 10")
                account.fixed_lots = round(value, 2)
            self._save()
        return account

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
                        "password_hash": acc.password_hash,
                        "avatar": acc.avatar,
                        "fixed_lots": acc.fixed_lots,
                        "follow_auto": acc.follow_auto,
                        "is_desk": False,
                        "first_name": acc.first_name or "",
                        "last_name": acc.last_name or "",
                        "email": acc.email or "",
                        "mt5_login": acc.mt5_login or "",
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

    @staticmethod
    def _parse_dt(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

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
        from app.models.domain import Position, PositionStatus, Side, TradeLog, TradeStatus

        restored_open = 0
        for row in raw:
            try:
                if row.get("is_desk"):
                    continue
                deposit = float(row.get("deposit") or self.settings.initial_balance)
                balance = float(row.get("balance") or deposit)
                broker, journal, risk = self._new_book(deposit)
                broker.balance = balance
                broker.deposit = deposit

                for t in row.get("trades") or []:
                    try:
                        status = TradeStatus(t.get("status", "CLOSED"))
                        ticket = t.get("ticket") or str(uuid.uuid4())
                        opened_at = self._parse_dt(t.get("opened_at")) or utcnow()
                        closed_at = self._parse_dt(t.get("closed_at"))
                        row_log = TradeLog(
                            id=t.get("id") or str(uuid.uuid4()),
                            ticket=ticket,
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
                            opened_at=opened_at,
                            closed_at=closed_at,
                        )
                        journal._trades.append(row_log)
                        journal._by_ticket[row_log.ticket] = row_log

                        # Rehydrate open positions so restart does not wipe / rewrite history.
                        if (
                            status == TradeStatus.OPEN
                            and row_log.entry is not None
                            and row_log.ticket
                        ):
                            broker.positions.append(
                                Position(
                                    id=row_log.ticket,
                                    symbol=row_log.symbol,
                                    side=row_log.side,
                                    lots=row_log.lots,
                                    entry_price=float(row_log.entry),
                                    stop_loss=row_log.stop_loss,
                                    take_profit=row_log.take_profit,
                                    strategy=row_log.strategy,
                                    status=PositionStatus.OPEN,
                                    unrealized_pnl=row_log.unrealized_pnl,
                                    opened_at=opened_at,
                                )
                            )
                            restored_open += 1
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
                    password_hash=row.get("password_hash") or None,
                    avatar=row.get("avatar") or None,
                    fixed_lots=(
                        float(row["fixed_lots"])
                        if row.get("fixed_lots") is not None
                        else None
                    ),
                    first_name=str(row.get("first_name") or ""),
                    last_name=str(row.get("last_name") or ""),
                    email=str(row.get("email") or ""),
                    mt5_login=self._restore_mt5_login(row),
                )
                risk.reset_daily(broker.balance)
                self._accounts[acc.id] = acc
                self._by_token[acc.token] = acc.id
                self._by_code[acc.code.upper()] = acc.id
            except Exception:  # noqa: BLE001
                log.exception("skip corrupt paper account row")
        log.info(
            "loaded %s paper accounts (%s open positions) from %s",
            len(self._accounts),
            restored_open,
            self.store_path,
        )
