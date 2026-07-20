from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.asia_sr_scalp import AsiaSrScalpStrategy
from app.strategies.auto_router import AutoStrategyRouter, Regime
from app.strategies.session import SessionTier, classify_session


def _bars(n: int, *, start: datetime, base: float = 2350.0) -> list[Candle]:
    bars: list[Candle] = []
    price = base
    for i in range(n):
        wave = ((i % 10) - 5) * 0.35
        o = price
        c = price + wave * 0.1
        h = max(o, c) + 0.6 + (0.8 if i % 10 == 2 else 0.0)
        l = min(o, c) - 0.6 - (0.8 if i % 10 == 7 else 0.0)
        price = c
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=h,
                low=l,
                close=c,
                period_seconds=300,
                open_time=start - timedelta(minutes=5 * (n - i)),
                is_closed=True,
            )
        )
    return bars


def test_asia_session_open_for_sr():
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    assert classify_session(ts).tier == SessionTier.ASIA


def test_auto_router_recommends_asia_sr_scalp():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2350.0 + ((i % 4) - 1.5) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_sr_scalp"
    assert d.regime == Regime.RANGE


def test_auto_router_recommends_asia_sr_on_mild_trend():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.8 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_sr_scalp"


def test_session_default_recommends_asia_sr():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    rec = router.session_default(ts)
    assert rec["strategy"] == "asia_sr_scalp"
    assert rec.get("recommended") is True


def test_blocks_outside_asia_desk():
    strat = AsiaSrScalpStrategy(news_filter=False, asia_only=True)
    outside = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = _bars(80, start=outside)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=outside,
    )
    assert strat.on_bar(bars, tick) is None
    assert any(c["name"] == "asia_session" and not c["ok"] for c in strat.last_checklist)


def test_exposes_sr_zones_on_asia_bars():
    strat = AsiaSrScalpStrategy(news_filter=False, asia_only=True)
    asia = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    bars = _bars(80, start=asia)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.05,
        ask=bars[-1].close + 0.05,
        mid=bars[-1].close,
        timestamp=asia,
    )
    signal = strat.on_bar(bars, tick)
    assert strat.last_range is not None
    assert isinstance(strat.last_zones, list)
    assert any(c["name"] == "asia_session" and c["ok"] for c in strat.last_checklist)
    if signal is not None:
        assert signal.strategy == "asia_sr_scalp"
        assert signal.side in {Side.BUY, Side.SELL}
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
