"""Trend_Breakout_ATR — Donchian + EMA200 + hard SL."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies import create_strategy, list_strategy_names
from app.strategies.session import classify_full_sessions
from app.strategies.trend_breakout_atr import TrendBreakoutAtrStrategy


def test_registered_and_seeded():
    assert "Trend_Breakout_ATR" in list_strategy_names()
    strat = create_strategy("Trend_Breakout_ATR")
    assert isinstance(strat, TrendBreakoutAtrStrategy)
    assert strat.channel_period == 20
    assert strat.reward_r == 2.5
    assert strat.min_adx == 18.0


def test_auto_session_new_york_maps_to_breakout():
    ts = datetime(2026, 7, 23, 17, 0, tzinfo=timezone.utc)
    window = classify_full_sessions(ts)
    assert window.label == "new_york"
    from app.strategies.session import FULL_SESSION_SLOTS

    ny = next(s for s in FULL_SESSION_SLOTS if s.label == "new_york")
    assert ny.strategy == "Trend_Breakout_ATR"


def test_waits_without_breakout():
    strat = TrendBreakoutAtrStrategy(news_filter=False, session_filter=False)
    now = datetime(2026, 7, 23, 17, 0, tzinfo=timezone.utc)
    bars = []
    price = 2350.0
    for i in range(220):
        t = now - timedelta(minutes=5 * (220 - i))
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=price + 0.3,
                low=price - 0.3,
                close=price + 0.05,
                volume=1,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
        price += 0.02
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=now,
    )
    assert strat.on_bar(bars, tick) is None
    assert strat.last_block_reason is not None


def test_buy_breakout_fires():
    strat = TrendBreakoutAtrStrategy(
        news_filter=False,
        session_filter=False,
        min_adx=0.0,
        min_break_atr=0.0,
        channel_period=10,
    )
    now = datetime(2026, 7, 23, 17, 0, tzinfo=timezone.utc)
    bars = []
    price = 2300.0
    # Gentle uptrend (keeps ATR modest) so EMA200 stays below price
    for i in range(220):
        t = now - timedelta(minutes=5 * (220 - i))
        step = 0.15
        o, c = price, price + step
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=c + 0.05,
                low=o - 0.05,
                close=c,
                volume=1,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
        price = c
    # Range the last 12 bars (~$1.2 wide), then close-break above
    base = bars[-13].close
    for i in range(-12, -1):
        b = bars[i]
        bars[i] = Candle(
            symbol="XAUUSD",
            open=base,
            high=base + 0.6,
            low=base - 0.6,
            close=base + 0.05,
            volume=1,
            period_seconds=300,
            open_time=b.open_time,
            timestamp=b.timestamp,
            is_closed=True,
        )
    last = bars[-1]
    break_px = base + 1.4
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=base + 0.2,
        high=break_px + 0.1,
        low=base,
        close=break_px,
        volume=1,
        period_seconds=300,
        open_time=last.open_time,
        timestamp=last.timestamp,
        is_closed=True,
    )
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=break_px - 0.1,
        ask=break_px + 0.1,
        mid=break_px,
        timestamp=now,
    )
    signal = strat.on_bar(bars, tick)
    assert signal is not None, strat.last_block_reason
    assert signal.side == Side.BUY
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.stop_loss < signal.take_profit
