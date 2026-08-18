"""Referral commissions — 5% of downline investment earnings."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.investment.registry import InvestmentAccount, InvestmentRegistry


def referral_rate() -> float:
    try:
        from app.core.config import get_settings

        return float(get_settings().invest_referral_rate)
    except Exception:  # noqa: BLE001
        return 0.05


def referral_link(code: str) -> str:
    from app.core.config import get_settings

    base = get_settings().portal_url.rstrip("/")
    return f"{base}/fx/?mode=register&ref={code.upper()}"


def credit_referral_commissions(
    registry: InvestmentRegistry,
    source: InvestmentAccount,
    earning_rows: list[dict],
) -> float:
    """Pay referrer 5% of each new downline earning row. Returns total commission."""
    if not source.referred_by or not earning_rows:
        return 0.0

    referrer = registry.get(source.referred_by)
    if referrer is None:
        return 0.0

    rate = referral_rate()
    total = 0.0
    for row in earning_rows:
        commission = round(float(row.get("earning") or 0) * rate, 4)
        if commission <= 0:
            continue
        referrer.referral_earned = round(referrer.referral_earned + commission, 4)
        total += commission
        referrer.referral_log.insert(
            0,
            {
                "date": row.get("date"),
                "from_account_id": source.id,
                "from_code": source.code,
                "from_label": source.label,
                "downline_earning": row.get("earning"),
                "commission": commission,
                "rate_pct": round(rate * 100, 2),
            },
        )
        referrer.referral_log = referrer.referral_log[:365]
        referrer._append_tx(
            "referral",
            commission,
            f"{round(rate * 100)}% from {source.code} ({source.label})",
        )
    return round(total, 4)


def referral_dashboard(registry: InvestmentRegistry, acc: InvestmentAccount) -> dict:
    rate = referral_rate()
    downline = [a for a in registry.list_all() if a.referred_by == acc.id]
    rows = []
    for child in downline:
        child.sync_accrual(registry)
        rows.append(
            {
                "account_code": child.code,
                "label": child.label,
                "balance": child.balance,
                "net_principal": child.net_principal,
                "total_earned": round(child.total_earned, 2),
            }
        )
    rows.sort(key=lambda r: r.get("balance") or 0, reverse=True)
    return {
        "referral_code": acc.code,
        "referral_link": referral_link(acc.code),
        "referral_rate_pct": round(rate * 100, 2),
        "referral_earned": round(acc.referral_earned, 2),
        "referral_count": len(downline),
        "referrals": rows,
        "recent_referral_earnings": acc.referral_log[:20],
    }
