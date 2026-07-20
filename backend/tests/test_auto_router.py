from datetime import datetime, timezone

from app.strategies.auto_router import AutoStrategyRouter, Regime


def test_weekend_blocks():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)  # Sunday
    prices = [2300 + i * 0.2 for i in range(80)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.strategy is None


def test_outside_asia_desk_blocks():
    router = AutoStrategyRouter(news_filter=False)
    # 14:00 UTC = 22:00 PH — after Asia desk close
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.strategy is None
    assert d.slot == "outside_asia_desk"


def test_asia_desk_range_picks_asia_scalp():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # PH 11:00
    prices = [2300.0 + ((i % 3) - 1) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_range_scalp"
    assert d.regime == Regime.RANGE
    assert d.slot == "asia"


def test_asia_desk_trend_picks_sr_scalp():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "gold_sr_scalp"
    assert d.slot == "asia"


def test_schedule_table_asia_desk():
    router = AutoStrategyRouter()
    table = router.schedule_table()
    assert len(table) >= 3
    asia = next(r for r in table if r["slot"] == "Asia scalp desk")
    assert "asia_range_scalp" in asia["strategies"]
    assert "gold_sr_scalp" in asia["strategies"]
