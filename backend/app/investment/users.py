"""Investor and admin user accounts."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.models.domain import utcnow

log = logging.getLogger(__name__)

PBKDF2_ITERS = 120_000


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iters),
        ).hex()
        return hmac.compare_digest(digest, check)
    except Exception:
        return False


@dataclass
class InvestUser:
    id: str
    email: str
    password_hash: str
    full_name: str
    role: str = "investor"
    account_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    def public(self) -> dict:
        return {
            "user_id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "account_id": self.account_id,
            "created_at": self.created_at.isoformat(),
        }

    def to_store(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "password_hash": self.password_hash,
            "full_name": self.full_name,
            "role": self.role,
            "account_id": self.account_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_store(cls, row: dict) -> InvestUser:
        created = row.get("created_at")
        created_at = (
            datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created
            else utcnow()
        )
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return cls(
            id=row["id"],
            email=row["email"].lower().strip(),
            password_hash=row["password_hash"],
            full_name=row.get("full_name") or "",
            role=row.get("role") or "investor",
            account_id=row.get("account_id"),
            created_at=created_at,
        )


class UserRegistry:
    def __init__(self, *, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._users: dict[str, InvestUser] = {}
        self._by_email: dict[str, str] = {}
        default = Path(__file__).resolve().parents[1] / "data" / "investment_users.json"
        self.store_path = store_path or default
        self._load()

    def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        account_id: str,
        role: str = "investor",
    ) -> InvestUser:
        email_norm = email.lower().strip()
        if not email_norm or "@" not in email_norm:
            raise ValueError("Valid email required")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        with self._lock:
            if email_norm in self._by_email:
                raise ValueError("Email already registered")
            user = InvestUser(
                id=str(uuid.uuid4()),
                email=email_norm,
                password_hash=hash_password(password),
                full_name=full_name.strip() or email_norm.split("@")[0],
                role=role,
                account_id=account_id,
            )
            self._users[user.id] = user
            self._by_email[email_norm] = user.id
            self._save()
        return user

    def authenticate(self, email: str, password: str) -> InvestUser | None:
        email_norm = email.lower().strip()
        with self._lock:
            uid = self._by_email.get(email_norm)
            if not uid:
                return None
            user = self._users.get(uid)
            if user is None or not verify_password(password, user.password_hash):
                return None
            return user

    def get(self, user_id: str) -> InvestUser | None:
        with self._lock:
            return self._users.get(user_id)

    def get_by_email(self, email: str) -> InvestUser | None:
        with self._lock:
            uid = self._by_email.get(email.lower().strip())
            return self._users.get(uid) if uid else None

    def list_all(self) -> list[InvestUser]:
        with self._lock:
            return list(self._users.values())

    def ensure_admin(
        self,
        *,
        email: str,
        password: str,
        full_name: str = "JM FX Admin",
        account_id: str | None = None,
    ) -> InvestUser:
        existing = self.get_by_email(email)
        if existing:
            return existing
        with self._lock:
            user = InvestUser(
                id=str(uuid.uuid4()),
                email=email.lower().strip(),
                password_hash=hash_password(password),
                full_name=full_name,
                role="admin",
                account_id=account_id,
            )
            self._users[user.id] = user
            self._by_email[user.email] = user.id
            self._save()
        return user

    def save(self) -> None:
        with self._lock:
            self._save()

    def _save(self) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [u.to_store() for u in self._users.values()]
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.store_path)
        except Exception:  # noqa: BLE001
            log.exception("failed to persist investment users")

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.exception("failed to load investment users")
            return
        if not isinstance(raw, list):
            return
        for row in raw:
            try:
                user = InvestUser.from_store(row)
                self._users[user.id] = user
                self._by_email[user.email] = user.id
            except Exception:  # noqa: BLE001
                log.exception("skip corrupt user row")
        log.info("loaded %s investment users", len(self._users))


_user_registry: UserRegistry | None = None


def get_user_registry() -> UserRegistry:
    global _user_registry
    if _user_registry is None:
        _user_registry = UserRegistry()
    return _user_registry
