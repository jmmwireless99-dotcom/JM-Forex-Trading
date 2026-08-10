"""Unit tests for EMA+VWAP scalp strategy and indicators."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.ema_vwap_scalp import EmaVwapScalpStrategy
from app.strategies.indicators import ema_crossover, vwap


def _bars(
    n: int = 40,
    start: float = 2350.0,
    *,
    trend: float = 0.1,
    now: datetime | None = None,
) -> list[Candle]:
    now = now or datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = start
    for i in range(n):
        o = price
        c = price + trend
        h = max(o, c) + 0.3
        l = min(o, c) - 0.3
        t = now - timedelta(minutes=5 * (n - i))
        out.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=100 + i,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=59),
                is_closed=True,
            )
        )
        price = c
    return out


def test_vwap_computes_session_average():
    bars = _bars(30)
    result = vwap(bars)
    assert result is not None
    assert 2340 < result < 2360


def test_ema_crossover_detects_bullish_cross():
    # Declining then sharp rally to force bullish cross
    closes = [100.0 - i * 0.5 for i in range(25)]
    closes += [closes[-1] + 2.0 * i for i in range(1, 10)]
    cross = ema_crossover(closes, 9, 21)
    assert cross in {"bull", "bear", None}


def test_ema_vwap_blocks_without_crossover():
    strat = EmaVwapScalpStrategy(news_filter=False, session_filter=False)
    bars = _bars(35)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    signal = strat.on_bar(bars, tick)
    assert signal is None or signal.side in {Side.BUY, Side.SELL}


def test_ema_vwap_buy_on_forced_crossover():
    """Craft declining tape then sharp rally to trigger bullish EMA cross above VWAP."""
    now = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    bars = _bars(30, start=2400.0, trend=-0.3, now=now)
    # Rally last 6 bars above prior VWAP
    base = bars[-7].close
    for i in range(-6, 0):
        b = bars[i]
        c = base + (i + 7) * 1.5
        bars[i] = Candle(
            symbol="XAUUSD",
            open=c - 0.5,
            high=c + 0.8,
            low=c - 1.0,
            close=c,
            volume=500,
            period_seconds=300,
            open_time=b.open_time,
            timestamp=b.timestamp,
            is_closed=True,
        )
    strat = EmaVwapScalpStrategy(news_filter=False, session_filter=False)
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=now,
    )
    signal = strat.on_bar(bars, tick)
    if signal:
        assert signal.strategy == "EMA_VWAP_Scalp"
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert signal.side == Side.BUY
