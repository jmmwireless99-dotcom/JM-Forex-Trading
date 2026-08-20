"""Investment registry — earnings persistence."""

from datetime import date, timedelta, timezone

from app.investment.registry import InvestmentAccount


def test_earnings_month_chart_includes_today():
    today = date.today()
    acc = InvestmentAccount(
        id="t",
        code="TST",
        label="Test",
        token="tok",
        total_deposited=1000,
        total_earned=10,
    )
    acc.earnings_log = [
        {
            "date": today.isoformat(),
            "earning": 1.0,
            "daily_rate_pct": 1.0,
            "balance_after": 1011.0,
        },
        {
            "date": (today - timedelta(days=1)).isoformat(),
            "earning": 0.99,
            "daily_rate_pct": 1.0,
            "balance_after": 1010.0,
        },
    ]
    chart = acc._earnings_month_chart()
    assert len(chart) >= 2
    assert chart[-1]["date"] == today.isoformat()
    assert chart[-1]["earning"] == 1.0
    assert any(r["earning"] == 0.0 for r in chart[: max(0, len(chart) - 2)])


def test_recent_earnings_keeps_31_days():
    acc = InvestmentAccount(id="t", code="TST", label="Test", token="tok")
    acc.earnings_log = [{"date": f"2026-01-{d:02d}", "earning": 1.0} for d in range(1, 40)]
    recent = acc._recent_earnings_view(limit=31)
    assert len(recent) == 31
