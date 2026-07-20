from datetime import datetime, timezone

from app.strategies.auto_router import AutoStrategyRouter, Regime


def test_weekend_blocks():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)  # Sunday
    prices = [2300 + i * 0.2 for i in range(80)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.strategy is None


def test_overlap_picks_strategy():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)  # Mon overlap
    # Build a clear uptrend
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy in {"gold_confluence", "gold_atr_trend"}
    assert d.slot == "london_ny_overlap"


def test_friday_late_blocks():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 24, 19, 0, tzinfo=timezone.utc)  # Friday 19:00
    prices = [2300 + i * 0.3 for i in range(80)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.slot == "friday_late"


def test_schedule_table_not_empty():
    router = AutoStrategyRouter()
    table = router.schedule_table()
    assert len(table) >= 4
    london = next(r for r in table if r["slot"] == "London")
    assert "RSI" not in london["strategies"]


def test_range_picks_sr_scalp():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)  # Mon London
    # Flat / choppy series → RANGE regime → gold_sr_scalp
    prices = [2300.0 + ((i % 3) - 1) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "gold_sr_scalp"
    assert d.regime == Regime.RANGE
