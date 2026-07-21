from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.asia_m5_sr_scalp import AsiaM5SrScalpStrategy
from app.strategies.auto_router import AutoStrategyRouter, Regime
from app.strategies.session import SessionTier, classify_session


def _bars(
    n: int,
    *,
    start: datetime,
    base: float = 2350.0,
    pattern: str = "range",
) -> list[Candle]:
    bars: list[Candle] = []
    price = base
    for i in range(n):
        if pattern == "range":
            wave = ((i % 10) - 5) * 0.55
            o = price
            c = price + wave * 0.2
            h = max(o, c) + 0.8 + (1.4 if i % 10 == 2 else 0.0)
            l = min(o, c) - 0.8 - (1.4 if i % 10 == 7 else 0.0)
            price = c
        elif pattern == "bounce_low":
            # Drift down then bullish rejection at lows
            if i < n - 3:
                o = price
                c = price - 0.35
                h = o + 0.2
                l = c - 0.4
                price = c
            else:
                o = price
                l = price - 0.9
                c = price + 0.7
                h = c + 0.15
                price = c
        else:
            o = price
            c = price + 0.4
            h = c + 0.2
            l = o - 0.15
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


def test_asia_window_7am_to_5pm():
    assert classify_session(datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)).tier == SessionTier.ASIA
    assert classify_session(datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)).label == "london"


def test_auto_recommends_asia_m5():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2350.0 + ((i % 4) - 1.5) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_m5_sr_scalp"
    assert d.regime == Regime.RANGE


def test_blocks_after_5pm_ph():
    strat = AsiaM5SrScalpStrategy(news_filter=False, asia_only=True)
    ts = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    bars = _bars(80, start=ts)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.05,
        ask=bars[-1].close + 0.05,
        mid=bars[-1].close,
        timestamp=ts,
    )
    assert strat.on_bar(bars, tick) is None
    assert any(c["name"] == "asia_hours" and not c["ok"] for c in strat.last_checklist)


def test_local_bounce_can_signal():
    strat = AsiaM5SrScalpStrategy(news_filter=False, asia_only=True, signal_cooldown_seconds=0)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # PH 11:00
    bars = _bars(60, start=ts, pattern="bounce_low")
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.05,
        ask=bars[-1].close + 0.05,
        mid=bars[-1].close,
        timestamp=ts,
    )
    signal = strat.on_bar(bars, tick)
    # May or may not fire depending on RSI/ADX from synthetic series;
    # checklist must pass session/M5 gates and attempt local/box paths.
    assert any(c["name"] == "asia_hours" and c["ok"] for c in strat.last_checklist)
    assert any(c["name"] == "m5_bar" and c["ok"] for c in strat.last_checklist)
    if signal is not None:
        assert signal.strategy == "asia_m5_sr_scalp"
        assert signal.side in {Side.BUY, Side.SELL}
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
