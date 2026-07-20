from datetime import datetime, timedelta, timezone

from app.engine.candles import CandleAggregator
from app.models.domain import Tick


def test_candle_forms_and_closes():
    agg = CandleAggregator(period_seconds=60, maxlen=50)
    base = datetime(2026, 7, 20, 14, 0, 10, tzinfo=timezone.utc)
    closed, forming = agg.update(
        Tick(symbol="XAUUSD", bid=2350, ask=2350.2, mid=2350.1, timestamp=base)
    )
    assert closed is None
    assert forming.open == 2350.1

    _, forming2 = agg.update(
        Tick(symbol="XAUUSD", bid=2351, ask=2351.2, mid=2351.1, timestamp=base + timedelta(seconds=20))
    )
    assert forming2.high == 2351.1
    assert forming2.low == 2350.1

    closed2, forming3 = agg.update(
        Tick(
            symbol="XAUUSD",
            bid=2349,
            ask=2349.2,
            mid=2349.1,
            timestamp=base + timedelta(seconds=60),
        )
    )
    assert closed2 is not None
    assert closed2.is_closed is True
    assert forming3.open == 2349.1
    hist = agg.history("XAUUSD")
    assert len(hist) >= 2
