"""NewsBreakout strategy and news-day auto routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.models.domain import Candle, Side, Tick
from app.strategies.auto_router import AutoStrategyRouter
from app.strategies.news_breakout import NewsBreakoutStrategy
from app.strategies.news_calendar import (
    check_news_trading_window,
    is_news_day,
    should_run_news_strategy,
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


def test_should_run_news_strategy_daytime_blocked():
    # 10AM PH on NFP day — still EMA_RSI, not NewsBreakout
    ts = datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc)
    armed = should_run_news_strategy(ts)
    assert armed.active is False
    assert "daytime" in armed.reason.lower()


def test_should_run_news_strategy_one_hour_before_nfp():
    # NFP 12:30 UTC — 11:30 UTC = 7:30 PM PH, T-60m
    ts = datetime(2026, 7, 3, 11, 30, tzinfo=timezone.utc)
    armed = should_run_news_strategy(ts)
    assert armed.active is True
    assert armed.event is not None
    assert "NFP" in armed.event


def test_should_run_news_strategy_too_early_even_at_night():
    # 9:30 PM PH but 3 hours before NFP
    ts = datetime(2026, 7, 3, 9, 30, tzinfo=timezone.utc)
    armed = should_run_news_strategy(ts)
    assert armed.active is False
    assert "T-60" in armed.reason or "in" in armed.reason


def test_news_trading_window_post_release():
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    armed = should_run_news_strategy(ts)
    assert armed.active is True
    window = check_news_trading_window(ts)
    assert window.active is True
    assert window.event is not None
    assert "NFP" in window.event


def test_news_trading_window_pre_release_armed_no_entry():
    ts = datetime(2026, 7, 3, 12, 32, tzinfo=timezone.utc)  # +2m after release
    assert should_run_news_strategy(ts).active is True
    window = check_news_trading_window(ts)
    assert window.active is False
    assert "pre-release" in window.reason.lower() or "wait" in window.reason.lower()


def test_auto_router_switches_one_hour_before_nfp_evening():
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 3, 11, 30, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    assert decision.strategy == "NewsBreakout"
    assert decision.allow_trading is True


def test_auto_router_uses_ai_ml_nfp_daytime():
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    assert decision.strategy == "AI_ML"
    assert decision.child_strategy == "EMA_RSI_Scalp"


def test_auto_router_uses_ai_ml_on_normal_day():
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 7, 18, 0, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    assert decision.strategy == "AI_ML"


def test_auto_router_news_breakout_disabled(monkeypatch):
    monkeypatch.setenv("JM_NEWS_BREAKOUT_AUTO", "false")
    get_settings.cache_clear()
    router = AutoStrategyRouter()
    ts = datetime(2026, 7, 3, 11, 30, tzinfo=timezone.utc)
    decision = router.decide(ts, [2500.0])
    get_settings.cache_clear()
    assert decision.strategy == "AI_ML"


def _news_break_bars(*, n: int = 18) -> list[Candle]:
    release = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    bars = _bars(n=n, base=2500.0, start=release.replace(hour=11, minute=30))
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
    return bars


def test_news_breakout_signals_buy_on_post_spike_break_legacy_mode():
    """require_retest=False preserves the old immediate-entry behavior."""
    strat = NewsBreakoutStrategy(require_retest=False)
    bars = _news_break_bars()
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    tick = _tick(ts, bid=2505.0)
    signal = strat.on_bar(bars, tick)
    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.strategy == "NewsBreakout"


def test_news_breakout_flags_pending_break_waits_for_retest():
    """Default (safer) mode: break alone does not fire — waits for retest."""
    strat = NewsBreakoutStrategy()
    assert strat.require_retest is True
    bars = _news_break_bars()
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    tick = _tick(ts, bid=2505.0)
    signal = strat.on_bar(bars, tick)
    assert signal is None
    assert strat._pending is not None
    assert strat._pending.side == Side.BUY
    assert "retest" in (strat.last_block_reason or "").lower()


def test_news_breakout_signals_on_retest_confirmation():
    """Pullback to the broken level + rejection candle fires the entry."""
    strat = NewsBreakoutStrategy()
    bars = _news_break_bars()
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    tick = _tick(ts, bid=2505.0)
    assert strat.on_bar(bars, tick) is None
    pending = strat._pending
    assert pending is not None
    level = pending.level

    retest = Candle(
        symbol="XAUUSD",
        open=level - 0.3,
        close=level + 0.1,
        high=level + 0.5,
        low=level - 0.5,
        volume=100,
        timestamp=ts + timedelta(minutes=5),
        open_time=ts + timedelta(minutes=5),
    )
    bars2 = [*bars, retest]
    tick2 = _tick(ts + timedelta(minutes=5), bid=level + 0.05)
    signal = strat.on_bar(bars2, tick2)
    assert signal is not None
    assert signal.side == Side.BUY
    assert "retest" in signal.reason.lower()
    assert strat._pending is None


def test_news_breakout_retest_timeout_drops_pending_no_chase():
    """If price never retests within the window, the setup is dropped (no chase)."""
    strat = NewsBreakoutStrategy(retest_valid_bars=2)
    bars = _news_break_bars()
    ts = datetime(2026, 7, 3, 12, 50, tzinfo=timezone.utc)
    tick = _tick(ts, bid=2505.0)
    assert strat.on_bar(bars, tick) is None
    assert strat._pending is not None

    # Price keeps running away — no pullback for 3 bars (> retest_valid_bars=2)
    running_bars = list(bars)
    timeout_reason: str | None = None
    for i in range(1, 4):
        b = Candle(
            symbol="XAUUSD",
            open=2506.0 + i,
            close=2507.0 + i,
            high=2507.5 + i,
            low=2505.5 + i,
            volume=100,
            timestamp=ts + timedelta(minutes=5 * i),
            open_time=ts + timedelta(minutes=5 * i),
        )
        running_bars.append(b)
        was_pending = strat._pending is not None
        tick_i = _tick(ts + timedelta(minutes=5 * i), bid=b.close)
        signal = strat.on_bar(running_bars, tick_i)
        assert signal is None
        if was_pending and strat._pending is None:
            timeout_reason = " ".join(strat.last_checklist)

    assert strat._pending is None
    assert timeout_reason is not None
    assert "missed" in timeout_reason.lower() or "skip" in timeout_reason.lower()


def test_news_breakout_blocks_daytime_on_news_day():
    strat = NewsBreakoutStrategy()
    bars = _bars(n=18)
    ts = datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc)
    tick = _tick(ts)
    assert strat.on_bar(bars, tick) is None
    assert "daytime" in (strat.last_block_reason or "").lower()
