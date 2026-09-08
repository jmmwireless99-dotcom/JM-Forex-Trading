"""Unit tests for Gold_Micro_Scalp (GOLD# / XAUUSD short-term)."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies import STRATEGY_REGISTRY, create_strategy
from app.strategies.gold_micro_scalp import GoldMicroScalpStrategy


def _bars(
    n: int = 50,
    start: float = 2650.0,
    *,
    trend: float = 0.15,
    now: datetime | None = None,
) -> list[Candle]:
    now = now or datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = start
    for i in range(n):
        o = price
        c = price + trend
        h = max(o, c) + 0.35
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


def test_registry_and_aliases():
    assert "Gold_Micro_Scalp" in STRATEGY_REGISTRY
    assert create_strategy("gold_micro").name == "Gold_Micro_Scalp"
    assert create_strategy("GOLD#").name == "Gold_Micro_Scalp"


def test_needs_warmup_bars():
    strat = GoldMicroScalpStrategy(news_filter=False, session_filter=False)
    bars = _bars(10)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    assert strat.on_bar(bars, tick) is None
    assert strat.last_block_reason and "Need" in strat.last_block_reason


def test_buy_on_uptrend_impulse():
    """Steady gold rally + oversized bullish body should print BUY."""
    now = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    bars = _bars(45, start=2600.0, trend=0.4, now=now)
    # Force a strong impulse on the last bar
    prev = bars[-2]
    impulse_close = prev.close + 3.5
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=prev.close + 0.2,
        high=impulse_close + 0.5,
        low=prev.close - 0.2,
        close=impulse_close,
        volume=800,
        period_seconds=300,
        open_time=bars[-1].open_time,
        timestamp=bars[-1].timestamp,
        is_closed=True,
    )
    strat = GoldMicroScalpStrategy(news_filter=False, session_filter=False)
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.15,
        ask=bars[-1].close + 0.15,
        mid=bars[-1].close,
        timestamp=now,
    )
    signal = strat.on_bar(bars, tick)
    assert signal is not None
    assert signal.strategy == "Gold_Micro_Scalp"
    assert signal.side == Side.BUY
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.take_profit > signal.stop_loss
    assert "GOLD_MICRO BUY" in signal.reason


def test_cooldown_blocks_immediate_reentry():
    now = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    bars = _bars(45, start=2600.0, trend=0.4, now=now)
    prev = bars[-2]
    impulse_close = prev.close + 3.5
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=prev.close + 0.2,
        high=impulse_close + 0.5,
        low=prev.close - 0.2,
        close=impulse_close,
        volume=800,
        period_seconds=300,
        open_time=bars[-1].open_time,
        timestamp=bars[-1].timestamp,
        is_closed=True,
    )
    strat = GoldMicroScalpStrategy(news_filter=False, session_filter=False)
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.15,
        ask=bars[-1].close + 0.15,
        mid=bars[-1].close,
        timestamp=now,
    )
    first = strat.on_bar(bars, tick)
    assert first is not None
    second = strat.on_bar(bars, tick)
    assert second is None
    assert strat.last_block_reason and "Cooldown" in strat.last_block_reason
