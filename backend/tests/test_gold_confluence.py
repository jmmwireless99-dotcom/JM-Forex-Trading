from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Tick
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


def _bars(n: int, start: float, ts: datetime, step: float = 0.5) -> list[Candle]:
    out: list[Candle] = []
    price = start
    for i in range(n):
        price += step
        out.append(
            Candle(
                symbol="XAUUSD",
                open=price - 0.3,
                high=price + 0.4,
                low=price - 0.5,
                close=price,
                period_seconds=300,
                open_time=ts - timedelta(minutes=5 * (n - i)),
                is_closed=True,
            )
        )
    return out


def test_indicator_helpers():
    values = [100 + i * 0.3 for i in range(60)]
    assert rsi(values, 14) is not None
    assert adx(values, 14) is not None


def test_ignores_non_gold():
    strategy = GoldConfluenceStrategy(session_filter=False, news_filter=False)
    assert (
        strategy.on_bar(
            [],
            Tick(symbol="EURUSD", bid=1.1, ask=1.1002, mid=1.1001),
        )
        is None
    )


def test_tick_path_disabled():
    strategy = GoldConfluenceStrategy(session_filter=False, news_filter=False)
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    assert strategy.evaluate(_tick(2300, ts)) is None


def test_news_filter_blocks_around_nfp():
    strategy = GoldConfluenceStrategy(
        session_filter=False,
        news_filter=True,
        min_atr=0.01,
        min_adx=1.0,
        fast=5,
        slow=12,
    )
    # First Friday Jul 2026 near 12:30 UTC
    ts = datetime(2026, 7, 3, 12, 25, tzinfo=timezone.utc)
    bars = _bars(80, 2300.0, ts)
    signal = strategy.on_bar(bars, _tick(bars[-1].close, ts))
    assert signal is None
    assert strategy.last_block_reason is not None
    assert "News" in strategy.last_block_reason or any(
        (not c["ok"] and c["name"] == "news") for c in strategy.last_checklist
    )


def test_confluence_checklist_populated():
    strategy = GoldConfluenceStrategy(
        fast=5,
        slow=12,
        atr_period=5,
        adx_period=5,
        rsi_period=5,
        min_adx=1.0,
        min_atr=0.01,
        pullback_atr=0.9,
        rsi_buy_low=0,
        rsi_buy_high=100,
        session_filter=False,
        news_filter=False,
        signal_cooldown_seconds=0,
    )
    ts = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    bars = _bars(60, 2300.0, ts, step=0.7)
    # stretch
    price = bars[-1].close
    for i in range(3):
        price += 2.2
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price - 1,
                high=price + 0.5,
                low=price - 1.2,
                close=price,
                period_seconds=300,
                open_time=ts - timedelta(minutes=5 * (4 - i)),
                is_closed=True,
            )
        )
    pull = price - 3.0
    bars.append(
        Candle(
            symbol="XAUUSD",
            open=price,
            high=price,
            low=pull,
            close=pull + 0.4,
            period_seconds=300,
            open_time=ts - timedelta(minutes=5),
            is_closed=True,
        )
    )
    confirm = pull + 2.5
    bars.append(
        Candle(
            symbol="XAUUSD",
            open=pull + 0.5,
            high=confirm + 0.2,
            low=pull + 0.3,
            close=confirm,
            period_seconds=300,
            open_time=ts,
            is_closed=True,
        )
    )
    signal = strategy.on_bar(bars, _tick(confirm, ts + timedelta(seconds=1)))
    assert len(strategy.last_checklist) >= 3
    if signal is not None:
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert signal.strategy == "gold_confluence"
