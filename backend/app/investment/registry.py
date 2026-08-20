"""Investment account registry — cash in/out, daily earnings, JSON persistence."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.investment.yield_calc import accrue_through, daily_earning, daily_rate, period_days, period_rate_pct
from app.models.domain import utcnow

log = logging.getLogger(__name__)


def _short_code() -> str:
    return secrets.token_hex(3).upper()


@dataclass
class InvestmentAccount:
    id: str
    code: str
    label: str
    token: str
    user_id: str | None = None
    referred_by: str | None = None
    total_deposited: float = 0.0
    total_withdrawn: float = 0.0
    principal_withdrawn: float = 0.0
    total_earned: float = 0.0
    referral_earned: float = 0.0
    last_accrual_date: date | None = None
    created_at: datetime = field(default_factory=utcnow)
    transactions: list[dict] = field(default_factory=list)
    earnings_log: list[dict] = field(default_factory=list)
    referral_log: list[dict] = field(default_factory=list)

    @property
    def net_principal(self) -> float:
        return max(0.0, round(self.total_deposited - self.principal_withdrawn, 2))

    @property
    def balance(self) -> float:
        return round(self.net_principal + self.total_earned + self.referral_earned, 2)

    def _append_tx(self, kind: str, amount: float, note: str = "") -> None:
        self.transactions.insert(
            0,
            {
                "id": str(uuid.uuid4()),
                "kind": kind,
                "amount": round(amount, 2),
                "note": note,
                "at": utcnow().isoformat(),
            },
        )
        self.transactions = self.transactions[:500]

    def _earnings_month_chart(self) -> list[dict]:
        """Daily earnings for the current calendar month (oldest → newest)."""
        today = utcnow().date()
        month_start = today.replace(day=1)
        by_date = {
            str(r.get("date")): r
            for r in self.earnings_log
            if r.get("date") and str(r["date"]) >= month_start.isoformat()
        }
        rate_pct = round(daily_rate() * 100, 4)
        rows: list[dict] = []
        cur = month_start
        while cur <= today:
            key = cur.isoformat()
            hit = by_date.get(key)
            rows.append(
                {
                    "date": key,
                    "earning": round(float(hit.get("earning") or 0), 4) if hit else 0.0,
                    "daily_rate_pct": float(hit.get("daily_rate_pct") or rate_pct) if hit else rate_pct,
                    "balance_after": round(float(hit.get("balance_after") or 0), 2) if hit else None,
                }
            )
            cur += timedelta(days=1)
        return rows

    def _recent_earnings_view(self, *, limit: int = 31) -> list[dict]:
        """Newest-first earnings rows — at least the last calendar month."""
        return list(self.earnings_log[: max(limit, 31)])

    def sync_accrual(self, registry=None) -> list[dict]:
        """Accrue missing daily earnings; pay referral commissions to upline."""
        base = self.net_principal + self.total_earned
        if base <= 0:
            return []

        new_total, rows, new_last = accrue_through(
            principal=base,
            last_accrual=self.last_accrual_date,
        )
        if new_total > 0 and rows:
            self.total_earned = round(self.total_earned + new_total, 4)
            self.last_accrual_date = new_last
            for row in rows:
                self.earnings_log.insert(0, row)
            # Keep ~3 years of daily rows — never drop recent history on deploy
            self.earnings_log = self.earnings_log[:1095]
            if registry is not None:
                from app.investment.referrals import credit_referral_commissions

                credit_referral_commissions(registry, self, rows)
        return rows

    def cash_in(self, amount: float, note: str = "", *, registry=None) -> dict:
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.sync_accrual(registry)
        self.total_deposited = round(self.total_deposited + amount, 2)
        self._append_tx("cash_in", amount, note or "Cash in")
        return self.dashboard(registry)

    def cash_out(self, amount: float, note: str = "", *, registry=None) -> dict:
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.sync_accrual(registry)
        if amount > self.balance + 0.001:
            raise ValueError("Insufficient balance")
        earned_pool = self.total_earned + self.referral_earned
        from_earned = min(amount, earned_pool)
        from_invest = min(from_earned, self.total_earned)
        from_referral = round(from_earned - from_invest, 4)
        from_principal = round(amount - from_earned, 2)
        self.total_earned = round(self.total_earned - from_invest, 4)
        self.referral_earned = round(self.referral_earned - from_referral, 4)
        self.principal_withdrawn = round(self.principal_withdrawn + from_principal, 2)
        self.total_withdrawn = round(self.total_withdrawn + amount, 2)
        self._append_tx("cash_out", amount, note or "Withdrawal")
        return self.dashboard(registry)

    def dashboard(self, registry=None) -> dict:
        self.sync_accrual(registry)
        today = utcnow().date()
        invest_base = self.net_principal + self.total_earned
        projected_today = (
            daily_earning(invest_base, today)
            if invest_base > 0
            else 0.0
        )
        period_pct = period_rate_pct()
        days = period_days()
        daily_pct = round(daily_rate(today) * 100, 4)

        dash = {
            "account_id": self.id,
            "account_code": self.code,
            "account_label": self.label,
            "currency": "USD",
            "period_rate_pct": period_pct,
            "period_days": days,
            "monthly_rate_pct": period_pct,
            "working_days_per_month": days,
            "daily_rate_pct": daily_pct,
            "total_deposited": round(self.total_deposited, 2),
            "total_withdrawn": round(self.total_withdrawn, 2),
            "net_principal": self.net_principal,
            "total_earned": round(self.total_earned, 2),
            "referral_earned": round(self.referral_earned, 2),
            "balance": self.balance,
            "projected_today": round(projected_today, 4),
            "last_accrual_date": (
                self.last_accrual_date.isoformat() if self.last_accrual_date else None
            ),
            "created_at": self.created_at.isoformat(),
            "recent_transactions": self.transactions[:50],
            "recent_earnings": self._recent_earnings_view(limit=31),
            "earnings_month_chart": self._earnings_month_chart(),
        }
        if registry is not None:
            from app.investment.referrals import referral_dashboard

            dash.update(referral_dashboard(registry, self))
        return dash

    def to_store(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "token": self.token,
            "user_id": self.user_id,
            "referred_by": self.referred_by,
            "total_deposited": self.total_deposited,
            "total_withdrawn": self.total_withdrawn,
            "principal_withdrawn": self.principal_withdrawn,
            "total_earned": self.total_earned,
            "referral_earned": self.referral_earned,
            "last_accrual_date": (
                self.last_accrual_date.isoformat() if self.last_accrual_date else None
            ),
            "created_at": self.created_at.isoformat(),
            "transactions": self.transactions,
            "earnings_log": self.earnings_log,
            "referral_log": self.referral_log,
        }

    @classmethod
    def from_store(cls, row: dict) -> InvestmentAccount:
        created = row.get("created_at")
        created_at = (
            datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created
            else utcnow()
        )
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        last = row.get("last_accrual_date")
        last_date = date.fromisoformat(last) if last else None

        return cls(
            id=row["id"],
            code=row.get("code") or _short_code(),
            label=row.get("label") or "Investor",
            token=row.get("token") or secrets.token_urlsafe(24),
            user_id=row.get("user_id"),
            referred_by=row.get("referred_by"),
            total_deposited=float(row.get("total_deposited") or 0),
            total_withdrawn=float(row.get("total_withdrawn") or 0),
            principal_withdrawn=float(row.get("principal_withdrawn") or 0),
            total_earned=float(row.get("total_earned") or 0),
            referral_earned=float(row.get("referral_earned") or 0),
            last_accrual_date=last_date,
            created_at=created_at,
            transactions=list(row.get("transactions") or []),
            earnings_log=list(row.get("earnings_log") or []),
            referral_log=list(row.get("referral_log") or []),
        )


class InvestmentRegistry:
    def __init__(self, *, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, InvestmentAccount] = {}
        self._by_token: dict[str, str] = {}
        default = Path(__file__).resolve().parents[1] / "data" / "investment_accounts.json"
        self.store_path = store_path or default
        self._load()

    def create(
        self,
        *,
        label: str | None = None,
        user_id: str | None = None,
        referred_by: str | None = None,
    ) -> InvestmentAccount:
        acc = InvestmentAccount(
            id=str(uuid.uuid4()),
            code=_short_code(),
            label=(label or "").strip() or "JM FX Investor",
            token=secrets.token_urlsafe(24),
            user_id=user_id,
            referred_by=referred_by,
        )
        with self._lock:
            self._accounts[acc.id] = acc
            self._by_token[acc.token] = acc.id
            self._save()
        return acc

    def get_by_referral_code(self, code: str) -> InvestmentAccount | None:
        needle = (code or "").strip().upper()
        if not needle:
            return None
        with self._lock:
            for acc in self._accounts.values():
                if acc.code.upper() == needle:
                    return acc
        return None

    def list_all(self) -> list[InvestmentAccount]:
        with self._lock:
            return list(self._accounts.values())

    def get(self, account_id: str) -> InvestmentAccount | None:
        with self._lock:
            return self._accounts.get(account_id)

    def require(self, account_id: str, token: str | None = None) -> InvestmentAccount:
        acc = self.get(account_id)
        if acc is None:
            raise KeyError("Investment account not found")
        if token and acc.token != token:
            raise PermissionError("Invalid investment token")
        return acc

    def save(self) -> None:
        with self._lock:
            self._save()

    def _save(self) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [a.to_store() for a in self._accounts.values()]
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.store_path)
        except Exception:  # noqa: BLE001
            log.exception("failed to persist investment accounts")

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.exception("failed to load investment accounts")
            return
        if not isinstance(raw, list):
            return
        for row in raw:
            try:
                acc = InvestmentAccount.from_store(row)
                self._accounts[acc.id] = acc
                self._by_token[acc.token] = acc.id
            except Exception:  # noqa: BLE001
                log.exception("skip corrupt investment row")
        log.info("loaded %s investment accounts", len(self._accounts))


_registry: InvestmentRegistry | None = None


def get_investment_registry() -> InvestmentRegistry:
    global _registry
    if _registry is None:
        _registry = InvestmentRegistry()
    return _registry
