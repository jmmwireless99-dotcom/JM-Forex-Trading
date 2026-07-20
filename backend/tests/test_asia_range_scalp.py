from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Tick
from app.strategies.asia_range_scalp import AsiaRangeScalpStrategy
from app.strategies.auto_router import AutoStrategyRouter, Regime
from app.strategies.session import SessionTier, classify_session


def test_asia_session_tier():
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # Tue 03:00
    s = classify_session(ts)
    assert s.tier == SessionTier.ASIA
    assert s.label == "asia"


def test_auto_router_picks_asia_scalp_when_ranging():
    router = AutoStrategyRouter(news_filter=False, min_trade_adx=20.0)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    # Flat series → RANGE / low ADX
    prices = [2350.0 + ((i % 4) - 1.5) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_range_scalp"
    assert d.regime == Regime.RANGE


def test_auto_router_blocks_asia_when_trending():
    router = AutoStrategyRouter(news_filter=False, min_trend_adx=25.0)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.9 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is False
    assert d.strategy is None


def test_asia_scalp_blocks_london_hours():
    strat = AsiaRangeScalpStrategy(news_filter=False, asia_only=True)
    london = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    bars = []
    price = 2350.0
    for i in range(40):
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=price + 0.8,
                low=price - 0.8,
                close=price + 0.1,
                period_seconds=300,
                open_time=london - timedelta(minutes=5 * (40 - i)),
                is_closed=True,
            )
        )
    tick = Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=london,
    )
    assert strat.on_bar(bars, tick) is None
    assert any(c["name"] == "asia_session" and not c["ok"] for c in strat.last_checklist)
