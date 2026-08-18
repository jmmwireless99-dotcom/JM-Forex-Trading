"""Bootstrap demo investor with fake money for trial earnings flow."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.config import get_settings
from app.investment.registry import get_investment_registry
from app.investment.users import get_user_registry
from app.models.domain import utcnow

log = logging.getLogger(__name__)


def bootstrap_investment_demo() -> None:
    """Ensure demo investor exists with fake deposit and accrued sample earnings."""
    settings = get_settings()
    if not settings.invest_demo_enabled:
        return

    users = get_user_registry()
    reg = get_investment_registry()
    email = settings.invest_demo_email.strip().lower()
    if not email:
        return

    user = users.get_by_email(email)
    acc = reg.get(user.account_id) if user and user.account_id else None

    if user is None:
        acc = reg.create(label=settings.invest_demo_name)
        user = users.register(
            email=email,
            password=settings.invest_demo_password,
            full_name=settings.invest_demo_name,
            account_id=acc.id,
        )
        acc.user_id = user.id
        log.info("created demo investor %s", email)
    elif acc is None:
        acc = reg.create(label=settings.invest_demo_name, user_id=user.id)
        user.account_id = acc.id

    if acc.total_deposited < 0.01:
        acc.cash_in(
            settings.invest_demo_deposit,
            "Demo fake money — trial only, not real funds",
        )
        today = utcnow().date()
        back = max(1, settings.invest_demo_backdate_days)
        acc.last_accrual_date = today - timedelta(days=back)
        acc.sync_accrual()
        log.info(
            "demo seeded $%s, earned $%s (backdate %s days)",
            acc.total_deposited,
            acc.total_earned,
            back,
        )
    elif acc.total_earned < 0.01 and acc.net_principal > 0:
        today = utcnow().date()
        back = max(1, settings.invest_demo_backdate_days)
        acc.last_accrual_date = today - timedelta(days=back)
        acc.sync_accrual()
        log.info("demo accrual catch-up, earned $%s", acc.total_earned)

    users.save()
    reg.save()
