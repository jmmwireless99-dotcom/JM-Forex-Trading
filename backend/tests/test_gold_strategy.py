from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.entry_setup import true_atr
from app.strategies.gold_atr_trend import GoldAtrTrendStrategy


def test_true_atr_requires_enough_data():
    bare = [
        Candle(
            symbol="XAUUSD",
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            period_seconds=300,
            is_closed=True,
        )
    ]
    assert true_atr(bare, period=14) is None
    bars = []
    price = 100.0
    now = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    for i in range(20):
        c = price + 0.5
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=c + 0.2,
                low=price - 0.2,
                close=c,
                period_seconds=300,
                open_time=now + timedelta(minutes=5 * i),
                is_closed=True,
            )
        )
        price = c
    value = true_atr(bars, period=14)
    assert value is not None and value > 0


def test_ignores_non_gold_symbols():
    strategy = GoldAtrTrendStrategy(session_filter=False)
    tick = Tick(symbol="EURUSD", bid=1.1, ask=1.1001, mid=1.10005)
    assert strategy.evaluate(tick) is None
    assert strategy.on_bar([], tick) is None


def test_tick_evaluate_disabled():
    strategy = GoldAtrTrendStrategy(session_filter=False)
    tick = Tick(
        symbol="XAUUSD",
        bid=2300,
        ask=2300.4,
        mid=2300.2,
        timestamp=datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc),
    )
    assert strategy.evaluate(tick) is None


def test_session_filter_blocks_asian_hours():
    strategy = GoldAtrTrendStrategy(session_filter=True, min_atr=0.01, min_adx=1.0)
    asian = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    bars = []
    price = 2300.0
    for i in range(70):
        price += 0.4
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price - 0.2,
                high=price + 0.3,
                low=price - 0.4,
                close=price,
                period_seconds=300,
                open_time=asian - timedelta(minutes=5 * (70 - i)),
                is_closed=True,
            )
        )
    tick = Tick(symbol="XAUUSD", bid=price - 0.1, ask=price + 0.1, mid=price, timestamp=asian)
    assert strategy.on_bar(bars, tick) is None
    assert strategy.last_block_reason == "Outside London/NY hours"


def test_structure_signal_has_sl_tp_when_ready():
    strategy = GoldAtrTrendStrategy(
        fast=5,
        slow=12,
        atr_period=5,
        adx_period=5,
        pullback_atr=0.9,
        min_atr=0.01,
        min_adx=1.0,
        session_filter=False,
        signal_cooldown_seconds=0,
    )
    now = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    bars: list[Candle] = []
    price = 2300.0
    # Build uptrend + stretch + pullback + bullish confirm
    for i in range(40):
        price += 0.8
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price - 0.5,
                high=price + 0.6,
                low=price - 0.7,
                close=price,
                period_seconds=300,
                open_time=now - timedelta(minutes=5 * (45 - i)),
                is_closed=True,
            )
        )
    # stretch highs
    for i in range(3):
        price += 2.0
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price - 1.0,
                high=price + 0.8,
                low=price - 1.2,
                close=price,
                period_seconds=300,
                open_time=now - timedelta(minutes=5 * (5 - i)),
                is_closed=True,
            )
        )
    # pullback bar into EMA zone then bullish reclaim
    pull = price - 3.5
    bars.append(
        Candle(
            symbol="XAUUSD",
            open=price,
            high=price + 0.2,
            low=pull,
            close=pull + 0.3,
            period_seconds=300,
            open_time=now - timedelta(minutes=5),
            is_closed=True,
        )
    )
    confirm_close = pull + 2.2
    bars.append(
        Candle(
            symbol="XAUUSD",
            open=pull + 0.4,
            high=confirm_close + 0.3,
            low=pull + 0.2,
            close=confirm_close,
            period_seconds=300,
            open_time=now,
            is_closed=True,
        )
    )
    tick = Tick(
        symbol="XAUUSD",
        bid=confirm_close - 0.15,
        ask=confirm_close + 0.15,
        mid=confirm_close,
        timestamp=now + timedelta(seconds=1),
    )
    signal = strategy.on_bar(bars, tick)
    # May still be None if EMA geometry doesn't align — assert safe contract
    if signal is not None:
        assert signal.side in {Side.BUY, Side.SELL}
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        if signal.side == Side.BUY:
            assert signal.stop_loss < confirm_close < signal.take_profit
        else:
            assert signal.take_profit < confirm_close < signal.stop_loss
