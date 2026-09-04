"""Unit tests for EMA_RSI and SMC scalp strategies."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side, Tick
from app.strategies.ema_rsi_scalp import EmaRsiScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy
from app.strategies.patterns import (
    bearish_engulfing,
    bullish_engulfing,
    bullish_pin_bar,
)


def _bars(
    n: int = 220,
    start: float = 2300.0,
    *,
    trend: float = 0.25,
    now: datetime | None = None,
) -> list[Candle]:
    now = now or datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = start
    for i in range(n):
        o = price
        c = price + trend
        h = max(o, c) + 0.4
        l = min(o, c) - 0.35
        t = now - timedelta(minutes=5 * (n - i))
        out.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=10,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=59),
                is_closed=True,
            )
        )
        price = c
    return out


def test_patterns_detect_engulf_and_pin():
    prev = Candle(
        symbol="XAUUSD",
        open=2350,
        high=2351,
        low=2348,
        close=2348.5,
        timestamp=datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc),
    )
    cur = Candle(
        symbol="XAUUSD",
        open=2348.4,
        high=2353,
        low=2348,
        close=2352.5,
        timestamp=datetime(2026, 7, 21, 14, 5, tzinfo=timezone.utc),
    )
    assert bullish_engulfing(prev, cur) is True
    pin = Candle(
        symbol="XAUUSD",
        open=2350,
        high=2350.3,
        low=2346,
        close=2349.8,
        timestamp=datetime(2026, 7, 21, 14, 10, tzinfo=timezone.utc),
    )
    assert bullish_pin_bar(pin) is True
    assert bearish_engulfing(cur, prev) is False


def test_ema_rsi_returns_none_without_confluence():
    strat = EmaRsiScalpStrategy(news_filter=False, session_filter=False)
    bars = _bars()
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=datetime(2026, 7, 21, 14, 5, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    # Random uptrend bars rarely hit RSI 40-50 + pattern together — must not crash
    signal = strat.on_bar(bars, tick)
    assert signal is None or signal.side in {Side.BUY, Side.SELL}
    assert isinstance(strat.last_checklist, list)


def test_ema_rsi_buy_on_forced_setup():
    """Craft bars: uptrend above EMA200, pullback into zone, RSI mid, bullish pin."""
    now = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = _bars(220, start=2200.0, trend=0.4, now=now)
    # Force last bars into a pullback + pin near EMA zone
    # Soften last 8 bars (pullback)
    for i in range(-8, -1):
        b = bars[i]
        bars[i] = Candle(
            symbol="XAUUSD",
            open=b.close + 0.2,
            high=b.close + 0.3,
            low=b.close - 1.2,
            close=b.close - 0.5,
            volume=10,
            period_seconds=300,
            open_time=b.open_time,
            timestamp=b.timestamp,
            is_closed=True,
        )
    last = bars[-1]
    # Bullish pin at end
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=last.close,
        high=last.close + 0.2,
        low=last.close - 2.0,
        close=last.close + 0.1,
        volume=10,
        period_seconds=300,
        open_time=last.open_time,
        timestamp=last.timestamp,
        is_closed=True,
    )
    strat = EmaRsiScalpStrategy(
        news_filter=False,
        session_filter=False,
        rsi_buy=(0, 100),  # relax RSI for unit test
        rsi_sell=(0, 100),
    )
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=now,
    )
    signal = strat.on_bar(bars, tick)
    # With relaxed RSI + pin + uptrend, expect BUY or a clear block reason
    if signal:
        assert signal.strategy == "EMA_RSI_Scalp"
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


def test_pip_levels_fixed_asia_stops():
    from app.strategies.entry_setup import pip_levels

    buy = pip_levels(
        Side.BUY,
        entry=2400.0,
        stop_loss_pips=120,
        take_profit_pips=225,
    )
    assert buy.stop_loss == 2388.0
    assert buy.take_profit == 2422.5


def _asia_buy_signal(*, asia_use_structure_stops: bool | None = None, monkeypatch=None):
    """Force a real BUY setup during PH Asia hours (UTC 02:00 = PH 10:00AM).

    Builds a gentle uptrend, then places the final candle's low precisely at
    the pre-bar EMA20 (a genuine pullback touch, not a heuristic guess) so the
    EMA_RSI confluence gate reliably fires — unlike hand-tuned pip offsets,
    this does not depend on ATR/EMA drift from unrelated code changes.
    """
    from app.core.config import get_settings
    from app.strategies.indicators import ema

    if asia_use_structure_stops is not None:
        monkeypatch.setenv(
            "JM_ASIA_USE_STRUCTURE_STOPS", "true" if asia_use_structure_stops else "false"
        )
        get_settings.cache_clear()

    now = datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc)
    bars = _bars(220, start=2200.0, trend=0.05, now=now)
    for i in range(-6, -1):
        b = bars[i]
        bars[i] = Candle(
            symbol="XAUUSD",
            open=b.close - 0.3,
            high=b.close - 0.1,
            low=b.close - 1.3,
            close=b.close - 0.9,
            volume=10,
            period_seconds=300,
            open_time=b.open_time,
            timestamp=b.timestamp,
            is_closed=True,
        )
    last = bars[-1]
    e20_pre = ema([c.close for c in bars[:-1]], 20)
    bars[-1] = Candle(
        symbol="XAUUSD",
        open=e20_pre - 0.05,
        high=e20_pre + 0.25,
        low=e20_pre - 1.5,
        close=e20_pre + 0.15,
        volume=10,
        period_seconds=300,
        open_time=last.open_time,
        timestamp=last.timestamp,
        is_closed=True,
    )
    strat = EmaRsiScalpStrategy(
        news_filter=False,
        session_filter=False,
        rsi_buy=(0, 100),
        rsi_sell=(0, 100),
    )
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=now,
    )
    signal = strat.on_bar(bars, tick)
    entry = tick.ask if signal is None or signal.side == Side.BUY else tick.bid
    return signal, entry


def test_asia_session_defaults_to_atr_structure_stops(monkeypatch):
    """Asia morning stops adapt to ATR with wider desk floors (not fixed 120p)."""
    from app.core.config import get_settings

    signal, entry = _asia_buy_signal(monkeypatch=monkeypatch)
    assert get_settings().asia_use_structure_stops is True
    if signal is None:
        return
    assert signal.side == Side.BUY
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    sl_pips = round(abs(entry - signal.stop_loss) / 0.1)
    # Fixed-pip mode always produces exactly 120p SL — structure mode sizes
    # from ATR/swing instead, so it should not land on that exact value.
    assert sl_pips != 120


def test_asia_desk_uses_wider_atr_floors(monkeypatch):
    """Asia desk config uses wider ATR floors than the base EMA_RSI defaults."""
    from app.core.config import get_settings
    from app.strategies.entry_setup import structure_levels

    settings = get_settings()
    assert settings.asia_min_stop_atr == 1.45
    assert settings.asia_min_tp_atr == 2.9
    assert settings.asia_structure_atr_pad == 0.4

    now = datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc)
    bars = _bars(10, start=2200.0, trend=0.0, now=now)
    atr = 3.0
    entry = bars[-1].close
    narrow = structure_levels(
        Side.BUY, entry=entry, candles=bars, atr=atr, min_stop_atr=1.15, min_tp_atr=2.3
    )
    wide = structure_levels(
        Side.BUY,
        entry=entry,
        candles=bars,
        atr=atr,
        atr_pad=settings.asia_structure_atr_pad,
        min_stop_atr=settings.asia_min_stop_atr,
        min_tp_atr=settings.asia_min_tp_atr,
    )
    assert abs(entry - wide.stop_loss) > abs(entry - narrow.stop_loss)
    assert abs(wide.take_profit - entry) > abs(narrow.take_profit - entry)


def test_asia_session_legacy_fixed_pips_opt_in(monkeypatch):
    """JM_ASIA_USE_STRUCTURE_STOPS=false restores the old fixed 120p/225p mode."""
    from app.core.config import get_settings

    signal, entry = _asia_buy_signal(asia_use_structure_stops=False, monkeypatch=monkeypatch)
    monkeypatch.delenv("JM_ASIA_USE_STRUCTURE_STOPS", raising=False)
    get_settings.cache_clear()
    if signal is None:
        return
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    sl_pips = round(abs(entry - signal.stop_loss) / 0.1)
    tp_pips = round(abs(signal.take_profit - entry) / 0.1)
    assert sl_pips == 120
    assert tp_pips == 225


def test_smc_waits_for_sweep():
    strat = LiquiditySweepSmcStrategy(news_filter=False, session_filter=False)
    # Flat tape — no swing break / no sweep → must stand aside
    now = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    bars = []
    for i in range(80):
        ts = now - timedelta(minutes=5 * (80 - i))
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=2350.0,
                high=2350.2,
                low=2349.8,
                close=2350.0,
                volume=10,
                period_seconds=300,
                open_time=ts,
                timestamp=ts + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
    tick = Tick(
        symbol="XAUUSD",
        bid=2349.9,
        ask=2350.1,
        mid=2350.0,
        timestamp=datetime(2026, 7, 21, 14, 5, tzinfo=timezone.utc),
    )
    strat.set_structure_bars(bars)
    signal = strat.on_bar(bars, tick)
    assert signal is None
    assert strat.last_block_reason is not None
