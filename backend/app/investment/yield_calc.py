"""Investment yield math — 30% in 30 calendar days."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


PERIOD_RATE = 0.30
PERIOD_DAYS = 30


def _settings_rates() -> tuple[float, int]:
    try:
        from app.core.config import get_settings

        s = get_settings()
        days = max(int(s.invest_period_days), 1)
        rate = float(s.invest_period_rate)
        return rate, days
    except Exception:  # noqa: BLE001
        return PERIOD_RATE, PERIOD_DAYS


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    return value


def daily_rate(day: date | datetime | None = None) -> float:
    rate, days = _settings_rates()
    return rate / days


def daily_earning(principal: float, day: date | datetime | None = None) -> float:
    if principal <= 0:
        return 0.0
    return round(principal * daily_rate(day), 4)


def iter_days(start: date, end: date):
    """Inclusive range of calendar days between start and end."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def accrue_through(
    *,
    principal: float,
    last_accrual: date | None,
    through: date | None = None,
) -> tuple[float, list[dict], date | None]:
    """Return (total_new_earnings, daily_rows, new_last_accrual)."""
    if principal <= 0:
        return 0.0, [], last_accrual

    today = _as_date(through or datetime.now(timezone.utc))
    if last_accrual is None:
        last_accrual = today - timedelta(days=1)

    start = last_accrual + timedelta(days=1)
    if start > today:
        return 0.0, [], last_accrual

    rate_pct = round(daily_rate() * 100, 4)
    rows: list[dict] = []
    total = 0.0
    last_day = last_accrual
    running = principal

    for day in iter_days(start, today):
        earn = daily_earning(running, day)
        if earn <= 0:
            continue
        total += earn
        running += earn
        rows.append(
            {
                "date": day.isoformat(),
                "principal": round(principal, 2),
                "earning": earn,
                "daily_rate_pct": rate_pct,
                "balance_after": round(running, 2),
            }
        )
        last_day = day

    new_last = last_day if rows else last_accrual
    return round(total, 4), rows, new_last


def period_rate_pct() -> float:
    rate, _ = _settings_rates()
    return round(rate * 100, 2)


def period_days() -> int:
    _, days = _settings_rates()
    return days
