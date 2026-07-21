from datetime import datetime, timezone

from app.strategies.auto_router import AutoStrategyRouter, Regime


def test_weekend_blocks():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)  # Sunday
    prices = [2300 + i * 0.2 for i in range(80)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.strategy is None


def test_asia_recommends_sr_scalp():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # PH 11:00
    prices = [2300.0 + ((i % 3) - 1) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_m5_sr_scalp"
    assert d.slot == "asia"


def test_london_after_asia_picks_strategy():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # late London
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy in {"gold_atr_trend", "gold_confluence", "gold_sr_scalp"}
    assert d.slot == "london"


def test_overlap_picks_atr_on_trend():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "gold_atr_trend"
    assert d.slot == "london_ny_overlap"


def test_session_default_next_session():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)
    rec = router.session_default(ts)
    assert rec["strategy"] == "asia_m5_sr_scalp"
    assert rec["next_session"]["strategy"] == "gold_confluence"
    assert rec["next_session"]["session"] == "london"


def test_schedule_table_full_desk():
    router = AutoStrategyRouter()
    table = router.schedule_table()
    assert len(table) >= 4
    asia = next(r for r in table if r["slot"] == "Asia")
    assert "asia_m5_sr_scalp" in asia["strategies"]
    london = next(r for r in table if "London" in r["slot"])
    assert "gold_confluence" in london["strategies"]
