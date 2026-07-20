from datetime import datetime, timezone

from app.models.domain import Side, Tick
from app.strategies.gold_confluence import GoldConfluenceStrategy
from app.strategies.indicators import adx, rsi


def _tick(price: float, ts: datetime) -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=price - 0.2,
        ask=price + 0.2,
        mid=price,
        timestamp=ts,
    )


def test_indicator_helpers():
    values = [100 + i * 0.3 for i in range(60)]
    assert rsi(values, 14) is not None
    assert adx(values, 14) is not None


def test_ignores_non_gold():
    strategy = GoldConfluenceStrategy(session_filter=False, news_filter=False)
    assert (
        strategy.on_tick(
            Tick(symbol="EURUSD", bid=1.1, ask=1.1002, mid=1.1001)
        )
        is None
    )


def test_news_filter_blocks_around_nfp():
    strategy = GoldConfluenceStrategy(session_filter=False, news_filter=True)
    # First Friday Jul 2026 near 12:30 UTC
    ts = datetime(2026, 7, 3, 12, 25, tzinfo=timezone.utc)
    price = 2300.0
    for _ in range(80):
        price += 0.4
        strategy.on_tick(_tick(price, ts))
    assert strategy.last_block_reason is not None
    assert "News" in strategy.last_block_reason or strategy.evaluate(_tick(price, ts)) is None


def test_confluence_can_emit_buy():
    strategy = GoldConfluenceStrategy(
        fast=5,
        slow=12,
        atr_period=5,
        adx_period=5,
        rsi_period=5,
        min_adx=1.0,
        min_atr=0.01,
        pullback_atr=0.35,
        rsi_buy_low=0,
        rsi_buy_high=100,
        session_filter=False,
        news_filter=False,
    )
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    price = 2300.0
    for _ in range(50):
        price += 0.7
        strategy.on_tick(_tick(price, ts))
    for _ in range(4):
        price += 2.5
        strategy.on_tick(_tick(price, ts))
    assert strategy._armed.get("XAUUSD") == Side.BUY

    signal = None
    for _ in range(15):
        price -= 0.6
        signal = strategy.on_tick(_tick(price, ts))
        if signal:
            break
    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.stop_loss is not None
    assert "confluence" in signal.reason.lower() or signal.strategy == "gold_confluence"
