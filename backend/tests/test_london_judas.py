"""Tests for London Judas session math + strategy gates."""

from datetime import datetime, timedelta, timezone

from app.brokers.paper import PaperBroker
from app.models.domain import Candle, OrderRequest, OrderType, Side, Tick
from app.strategies.london_judas_sweep import (
    LondonJudasSweepStrategy,
    find_bearish_fvg,
    find_bullish_fvg,
)
from app.strategies.london_session import (
    calculate_asian_range,
    is_london_entry_window,
    is_past_pending_kill,
    pending_expire_at,
)


def _candle(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="XAUUSD",
        open=o,
        high=h,
        low=l,
        close=c,
        volume=5,
        period_seconds=300,
        open_time=ts,
        timestamp=ts + timedelta(minutes=4, seconds=50),
        is_closed=True,
    )


def test_london_windows():
    assert is_london_entry_window(datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc))
    assert not is_london_entry_window(datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc))
    assert is_past_pending_kill(datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc))
    exp = pending_expire_at(datetime(2026, 7, 21, 8, 15, tzinfo=timezone.utc))
    assert exp.hour == 12 and exp.tzinfo is not None


def test_asian_range_calculator():
    day = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    bars = []
    # Asia 00:00–06:00 UTC
    for h in range(0, 6):
        for m in (0, 30):
            ts = datetime(2026, 7, 21, h, m, tzinfo=timezone.utc)
            bars.append(_candle(ts, 2350, 2355 if h == 2 else 2352, 2348 if h == 4 else 2349, 2351))
    asian = calculate_asian_range(bars, as_of=day)
    assert asian is not None
    assert asian.high == 2355
    assert asian.low == 2348
    assert asian.range_pips == 700.0  # 7.0 / 0.01


def test_fvg_helpers():
    t0 = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    bear = [
        _candle(t0, 2360, 2362, 2358, 2359),
        _candle(t0 + timedelta(minutes=5), 2359, 2360, 2355, 2356),
        _candle(t0 + timedelta(minutes=10), 2356, 2357, 2350, 2351),
    ]
    # a.low 2358 > c.high 2357 → bearish FVG
    fvg = find_bearish_fvg(bear)
    assert fvg is not None
    assert fvg.bias == "SELL"
    assert fvg.mid == round((2358 + 2357) / 2, 2)


def test_strategy_blocks_outside_london():
    strat = LondonJudasSweepStrategy(news_filter=False)
    bars = [_candle(datetime(2026, 7, 21, 3, i, tzinfo=timezone.utc), 2350, 2351, 2349, 2350) for i in range(40)]
    tick = Tick(
        symbol="XAUUSD",
        bid=2350,
        ask=2350.2,
        mid=2350.1,
        timestamp=datetime(2026, 7, 21, 3, 30, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    assert strat.on_bar(bars, tick) is None
    assert "Outside London" in (strat.last_block_reason or "")


def test_multi_bar_judas_sell_after_remembered_sweep():
    """Sweep on bar A, ChoCH+FVG on later bars → LIMIT SELL (not same-candle only)."""
    strat = LondonJudasSweepStrategy(news_filter=False)
    bars: list[Candle] = []
    # Asia 00:00–06:00 — tight box 2350–2352
    for h in range(0, 6):
        for m in (0, 30):
            ts = datetime(2026, 7, 21, h, m, tzinfo=timezone.utc)
            bars.append(_candle(ts, 2351, 2352, 2350, 2351))

    t = datetime(2026, 7, 21, 7, 0, tzinfo=timezone.utc)
    bars.append(_candle(t, 2351, 2352.2, 2350.5, 2351.2))
    bars.append(_candle(t + timedelta(minutes=5), 2351.2, 2352.0, 2350.8, 2351.0))

    # Sweep bar 07:15 — wick +$1.20 above Asia high (2352), close back inside
    sweep_ts = t + timedelta(minutes=15)
    bars.append(_candle(sweep_ts, 2351.5, 2353.2, 2351.0, 2351.8))

    # Later bars: displacement + bearish FVG (a.low 2351.5 > c.high 2350.5)
    bars.append(_candle(sweep_ts + timedelta(minutes=5), 2351.8, 2352.0, 2351.5, 2351.6))
    bars.append(_candle(sweep_ts + timedelta(minutes=10), 2351.6, 2351.7, 2349.0, 2349.2))
    bars.append(_candle(sweep_ts + timedelta(minutes=15), 2349.2, 2350.5, 2348.0, 2348.5))

    tick = Tick(
        symbol="XAUUSD",
        bid=2348.4,
        ask=2348.6,
        mid=2348.5,
        timestamp=sweep_ts + timedelta(minutes=15),
    )
    strat.set_structure_bars(bars)
    sig = strat.on_bar(bars, tick)
    assert sig is not None
    assert sig.side == Side.SELL
    assert sig.order_type == OrderType.LIMIT
    assert sig.limit_price == 2351.0
    assert sig.sweep_price == 2353.2
    assert sig.expire_at is not None and sig.expire_at.hour == 12


def test_paper_limit_order_and_kill():
    broker = PaperBroker(1000)
    tick = Tick(
        symbol="XAUUSD",
        bid=2350.0,
        ask=2350.2,
        mid=2350.1,
        timestamp=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
    )
    broker.update_tick(tick)
    order = broker.place_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.SELL,
            lots=0.01,
            order_type=OrderType.LIMIT,
            limit_price=2355.0,
            stop_loss=2360.0,
            take_profit=2340.0,
            expire_at=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
            strategy="London_Judas_Sweep",
        )
    )
    assert order.status.value == "PENDING"
    # Price never reaches limit — kill at 12:00
    broker.cancel_pending(reason="kill")
    assert broker.pending_orders() == []
