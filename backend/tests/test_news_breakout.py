"""NewsBreakout strategy and news-day auto routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.models.domain import Candle, Side, Tick
from app.strategies.auto_router import AutoStrategyRouter
from app.strategies.news_breakout import NewsBreakoutStrategy
from app.strategies.news_calendar import (
    check_news_trading_window,
    is_news_day,
    primary_news_event,
)


def _tick(ts: datetime, *, bid: float = 2500.0) -> Tick:
    return Tick(symbol="XAUUSD", bid=bid, ask=bid + 0.10, mid=bid + 0.05, timestamp=ts)


def _bars(
    *,
    n: int = 20,
    base: float = 2500.0,
    start: datetime | None = None,
) -> list[Candle]:
    start = start or datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        lo = base - 1.0
        hi = base + 1.0
        out.append(
            Candle(
                symbol="XAUUSD",
                open=base,
                high=hi,
                low=lo,
                close=base,
                volume=100,
                timestamp=ts,
                open_time=ts,
            )
        )
    return out


def test_is_news_day_nfp_first_friday():
    ts = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)
    assert is_news_day(ts) is True
    primary = primary_news_event(ts)
    assert primary is not None
    assert "NFP" in primary.event.name


def test_quiet_day_not_news_day():
    ts = datetime(2026, 7, 7, 8, 0, tzinfo=timezone.utc)
    assert is_news_day(ts) is False


def test_news_trading_window_post_release():
    # NFP 12:30 UTC — active at +20 min
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    window = check_news_trading_window(ts)
    assert window.active is True
    assert window.event is not None
    assert "NFP" in window.event


def test_news_trading_window_too_early():
    ts = datetime(2026, 7, 3, 12, 32, tzinfo=timezone.utc)  # +2m only
    window = check_news_trading_window(ts)
    assert window.active is False


def test_auto_router_switches_to_news_breakout_on_nfp_day():
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc)  # 10AM PH Asia
    decision = router.decide(ts, [2500.0])
    assert decision.strategy == "NewsBreakout"
    assert decision.allow_trading is True
    assert "News day" in decision.reason


def test_auto_router_uses_ai_ml_on_normal_day():
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 7, 2, 0, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    assert decision.strategy == "AI_ML"
    assert decision.child_strategy == "EMA_RSI_Scalp"


def test_auto_router_news_breakout_disabled(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("JM_NEWS_BREAKOUT_AUTO", "false")
    get_settings.cache_clear()
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    get_settings.cache_clear()
    assert decision.strategy == "AI_ML"


def test_news_breakout_signals_buy_on_post_spike_break():
    strat = NewsBreakoutStrategy()
    release = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    bars = _bars(n=18, base=2500.0, start=release.replace(hour=11, minute=30))
    # Pre-range flat, then strong bullish break
    for b in bars[:-1]:
        b.high = 2501.0
        b.low = 2499.0
        b.close = 2500.0
        b.open = 2500.0
    last = bars[-1]
    last.open = 2500.0
    last.close = 2505.0
    last.high = 2505.5
    last.low = 2499.5

    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    tick = _tick(ts, bid=2505.0)
    signal = strat.on_bar(bars, tick)
    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.strategy == "NewsBreakout"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None


def test_news_breakout_blocks_outside_window():
    strat = NewsBreakoutStrategy()
    bars = _bars(n=12)
    ts = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)  # news day but pre-release
    tick = _tick(ts)
    assert strat.on_bar(bars, tick) is None
    assert "post-release" in (strat.last_block_reason or "").lower()
