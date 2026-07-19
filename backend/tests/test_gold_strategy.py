from datetime import datetime, timezone

from app.models.domain import Side, Tick
from app.strategies.gold_atr_trend import GoldAtrTrendStrategy, atr


def test_atr_requires_enough_data():
    assert atr([1, 2, 3], period=14) is None
    values = [100 + i * 0.5 for i in range(20)]
    value = atr(values, period=14)
    assert value is not None
    assert value > 0


def test_ignores_non_gold_symbols():
    strategy = GoldAtrTrendStrategy(session_filter=False)
    tick = Tick(symbol="EURUSD", bid=1.1, ask=1.1001, mid=1.10005)
    assert strategy.on_tick(tick) is None


def _tick(price: float, ts: datetime) -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=price - 0.2,
        ask=price + 0.2,
        mid=price,
        timestamp=ts,
    )


def test_gold_atr_trend_emits_buy_with_atr_stops():
    strategy = GoldAtrTrendStrategy(
        fast=5,
        slow=12,
        atr_period=5,
        pullback_atr=0.35,
        min_atr=0.01,
        sl_atr=1.8,
        tp_atr=2.7,
        session_filter=False,
    )
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)

    # Steady uptrend to establish EMAs
    price = 2300.0
    for _ in range(40):
        price += 0.6
        strategy.on_tick(_tick(price, ts))

    # Stretch above fast EMA to arm BUY
    for _ in range(4):
        price += 2.5
        strategy.on_tick(_tick(price, ts))
    assert strategy._armed.get("XAUUSD") == Side.BUY

    # Mild pullback toward EMA while staying in uptrend
    signal = None
    for _ in range(12):
        price -= 0.7
        signal = strategy.on_tick(_tick(price, ts))
        if signal:
            break

    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.symbol == "XAUUSD"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.stop_loss < price < signal.take_profit


def test_session_filter_blocks_asian_hours():
    strategy = GoldAtrTrendStrategy(
        session_filter=True,
        fast=3,
        slow=5,
        atr_period=3,
        min_atr=0.01,
    )
    asian = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    price = 2300.0
    for _ in range(40):
        price += 0.5
        assert strategy.on_tick(_tick(price, asian)) is None
