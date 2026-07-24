"""BTCUSD best strategy — registry, symbol gate, preferred save."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies import create_strategy, list_strategy_names
from app.strategies.btc_ema_rsi import BtcEmaRsiScalpStrategy


def test_btc_strategy_registered():
    assert "BTC_EMA_RSI_Scalp" in list_strategy_names()
    strat = create_strategy("BTC_EMA_RSI_Scalp")
    assert isinstance(strat, BtcEmaRsiScalpStrategy)
    assert strat.symbol == "BTCUSD"
    assert strat.reward_r == 2.2
    assert strat.allow_soft_confirm is False


def test_btc_ignores_xau_ticks():
    strat = BtcEmaRsiScalpStrategy(news_filter=False)
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    bars = []
    price = 95000.0
    for i in range(220):
        t = now - timedelta(minutes=5 * (220 - i))
        o, c = price, price + 10
        bars.append(
            Candle(
                symbol="BTCUSD",
                open=o,
                high=max(o, c) + 5,
                low=min(o, c) - 5,
                close=c,
                volume=1,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
        price = c
    strat.set_structure_bars(bars)
    gold_tick = Tick(
        symbol="XAUUSD",
        bid=4000.0,
        ask=4000.2,
        mid=4000.1,
        timestamp=now,
    )
    assert strat.on_bar(bars, gold_tick) is None
    assert "BTCUSD" in (strat.last_block_reason or "")
