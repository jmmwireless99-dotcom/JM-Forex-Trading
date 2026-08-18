"""Unit tests for Liquidity Sweep SMC strategy fixes."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.liquidity_sweep_smc import (
    LiquiditySweepSmcStrategy,
    _wick_swept_high,
    _wick_swept_low,
)


def _bar(
    ts: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
) -> Candle:
    return Candle(
        symbol="XAUUSD",
        open=o,
        high=h,
        low=l,
        close=c,
        volume=100,
        period_seconds=300,
        open_time=ts,
        timestamp=ts + timedelta(minutes=4, seconds=59),
        is_closed=True,
    )


def test_wick_sweep_detects_rejection_not_breakout():
    level = 2355.0
    pad = 0.1
    # Upper wick sweep with bearish close still below level
    assert _wick_swept_high(_bar(datetime.now(timezone.utc), 2354.8, 2355.5, 2354.5, 2354.9), level, pad)
    # Clean breakout — body above level
    assert not _wick_swept_high(_bar(datetime.now(timezone.utc), 2355.2, 2356.0, 2355.0, 2355.8), level, pad)
    # Lower wick sweep
    assert _wick_swept_low(_bar(datetime.now(timezone.utc), 2350.2, 2350.5, 2349.4, 2350.1), 2350.0, pad)


def test_smc_waits_for_sweep_on_flat_tape():
    strat = LiquiditySweepSmcStrategy(news_filter=False, session_filter=False)
    now = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = [
        _bar(now - timedelta(minutes=5 * (80 - i)), 2350.0, 2350.2, 2349.8, 2350.0)
        for i in range(80)
    ]
    tick = Tick(
        symbol="XAUUSD",
        bid=2349.9,
        ask=2350.1,
        mid=2350.0,
        timestamp=datetime(2026, 7, 21, 14, 5, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    signal = strat.on_bar(bars, tick)
    assert signal is None
    assert "sweep" in (strat.last_block_reason or "").lower()


def test_smc_enters_on_asia_high_sweep_rejection():
    now = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = []
    for i in range(84):
        ts = datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i)
        bars.append(_bar(ts, 2352.0, 2355.0, 2348.0, 2352.5))
    # overlap drift up
    for i in range(84, 95):
        ts = datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i)
        bars.append(_bar(ts, 2353.5, 2354.2, 2353.0, 2353.8))
    # sweep bar at asia high 2355
    ts = datetime(2026, 7, 21, 7, 55, tzinfo=timezone.utc)
    bars.append(_bar(ts, 2354.5, 2355.6, 2354.2, 2354.7))
    strat = LiquiditySweepSmcStrategy(news_filter=False, session_filter=False)
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=2354.6,
        ask=2354.8,
        mid=2354.7,
        timestamp=ts + timedelta(minutes=1),
    )
    signal = strat.on_bar(bars, tick)
    assert signal is not None
    assert signal.strategy == "Liquidity_Sweep_SMC"
    assert signal.side == Side.SELL
    assert signal.stop_loss is not None
    assert signal.take_profit is not None


def test_smc_choppy_market_can_fire_after_sweep():
    """Sinusoidal chop should eventually produce a sweep + entry."""
    import math

    now = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = []
    for i in range(120):
        ts = datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i)
        base = 2352 + 3 * math.sin(i / 5)
        bars.append(_bar(ts, base - 0.2, base + 1.2, base - 1.2, base + 0.1))
    strat = LiquiditySweepSmcStrategy(news_filter=False, session_filter=False)
    fired = 0
    for i in range(80, 120):
        sub = bars[: i + 1]
        strat.set_structure_bars(sub)
        tick = Tick(
            symbol="XAUUSD",
            bid=sub[-1].close - 0.1,
            ask=sub[-1].close + 0.1,
            mid=sub[-1].close,
            timestamp=sub[-1].timestamp + timedelta(seconds=30),
        )
        if strat.on_bar(sub, tick):
            fired += 1
    assert fired >= 1
