"""Tests for London session clocks + Asian range (no Judas strategy)."""

from datetime import datetime, timedelta, timezone

from app.brokers.paper import PaperBroker
from app.models.domain import Candle, OrderRequest, OrderType, Side, Tick
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
    for h in range(0, 6):
        for m in (0, 30):
            ts = datetime(2026, 7, 21, h, m, tzinfo=timezone.utc)
            bars.append(_candle(ts, 2350, 2355 if h == 2 else 2352, 2348 if h == 4 else 2349, 2351))
    asian = calculate_asian_range(bars, as_of=day)
    assert asian is not None
    assert asian.high == 2355
    assert asian.low == 2348
    assert asian.range_pips == 700.0


def test_paper_limit_kill_switch():
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
            strategy="Liquidity_Sweep_SMC",
        )
    )
    assert order.status.value == "PENDING"
    broker.cancel_pending(reason="kill")
    assert broker.pending_orders() == []
