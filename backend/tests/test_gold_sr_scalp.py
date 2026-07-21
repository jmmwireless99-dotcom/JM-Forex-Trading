from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.auto_router import AutoStrategyRouter, Regime
from app.strategies.gold_sr_scalp import GoldSrScalpStrategy
from app.strategies.session import SessionTier, classify_session


def _bars(
    n: int,
    *,
    base: float = 2350.0,
    start: datetime,
    pattern: str = "range",
) -> list[Candle]:
    bars: list[Candle] = []
    price = base
    for i in range(n):
        if pattern == "range":
            # Gentle oscillation with clear swing highs/lows
            wave = ((i % 10) - 5) * 0.35
            o = price
            c = price + wave * 0.1
            h = max(o, c) + 0.6 + (0.8 if i % 10 == 2 else 0.0)
            l = min(o, c) - 0.6 - (0.8 if i % 10 == 7 else 0.0)
            price = c
        else:
            o = price
            c = price + 0.4
            h = c + 0.3
            l = o - 0.2
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


def test_asia_desk_allows_sr_scalp_session():
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # PH 11:00
    assert classify_session(ts).tier == SessionTier.ASIA


def test_auto_router_asia_uses_asia_sr_not_gold_sr():
    router = AutoStrategyRouter(news_filter=False, min_trend_adx=25.0)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2200 + i * 0.9 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_m3m5_sr_scalp"
    assert d.slot == "asia"


def test_auto_router_asia_range_uses_asia_sr():
    router = AutoStrategyRouter(news_filter=False, min_trade_adx=20.0)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2350.0 + ((i % 4) - 1.5) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_m3m5_sr_scalp"
    assert d.regime == Regime.RANGE


def test_evaluate_returns_none():
    strat = GoldSrScalpStrategy(session_filter=False, news_filter=False)
    tick = Tick(
        symbol="XAUUSD",
        bid=2349.0,
        ask=2351.0,
        mid=2350.0,
        timestamp=datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc),
    )
    assert strat.evaluate(tick) is None


def test_blocks_off_hours_when_session_filter_on():
    strat = GoldSrScalpStrategy(session_filter=True, news_filter=False)
    off = datetime(2026, 7, 21, 21, 0, tzinfo=timezone.utc)  # off-hours
    bars = _bars(80, start=off)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=off,
    )
    assert strat.on_bar(bars, tick) is None
    assert any(c["name"] == "session" and not c["ok"] for c in strat.last_checklist)


def test_allows_asia_desk_when_session_filter_on():
    strat = GoldSrScalpStrategy(session_filter=True, news_filter=False)
    asia = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    bars = _bars(80, start=asia)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=asia,
    )
    # May or may not signal; session gate must pass
    strat.on_bar(bars, tick)
    assert any(c["name"] == "session" and c["ok"] for c in strat.last_checklist)


def test_detects_zones_and_exposes_last_zones():
    strat = GoldSrScalpStrategy(session_filter=False, news_filter=False)
    asia = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    bars = _bars(80, start=asia, pattern="range")
    # Force a bullish rejection into a demand area near recent low
    low = min(c.low for c in bars[-25:-3])
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=low + 0.2,
        high=low + 1.2,
        low=low - 0.1,
        close=low + 1.0,
        period_seconds=300,
        open_time=asia - timedelta(minutes=5),
        is_closed=True,
    )
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.05,
        ask=bars[-1].close + 0.05,
        mid=bars[-1].close,
        timestamp=asia,
    )
    signal = strat.on_bar(bars, tick)
    assert isinstance(strat.last_zones, list)
    assert len(strat.last_checklist) >= 2
    # May or may not fire depending on swing detection; zones should populate
    assert strat.last_zones or strat.last_block_reason is not None
    if signal is not None:
        assert signal.strategy == "gold_sr_scalp"
        assert signal.side in {Side.BUY, Side.SELL}
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


def test_schedule_mentions_asia_m3m5_sr_scalp():
    table = AutoStrategyRouter().schedule_table()
    asia = next(r for r in table if "Asia" in r["slot"])
    assert "asia_m3m5_sr_scalp" in asia["strategies"]
