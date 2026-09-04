from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side
from app.strategies.entry_setup import structure_levels, true_atr, volatility_stop_scale
from app.strategies.manual_only import ManualOnlyStrategy
from app.models.domain import Tick


def _bars(n: int = 80, start: float = 2300.0) -> list[Candle]:
    now = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = start
    for i in range(n):
        # Uptrend with pullbacks
        o = price
        c = price + (0.35 if i % 5 else -0.15)
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
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


def test_true_atr_and_structure_sl_tp():
    bars = _bars()
    atr = true_atr(bars, 14)
    assert atr is not None and atr > 0
    levels = structure_levels(Side.BUY, entry=bars[-1].close, candles=bars, atr=atr)
    assert levels.stop_loss < bars[-1].close
    assert levels.take_profit > bars[-1].close
    assert levels.reward_r >= 2.0


def test_volatility_stop_scale_wider_on_burst():
    bars = _bars()
    atr = true_atr(bars, 14)
    assert atr is not None
    _, calm_mult = volatility_stop_scale(bars, atr)
    assert calm_mult >= 1.0

    # Inject a fast burst on the last 3 bars
    burst = list(bars)
    for i in (-3, -2, -1):
        c = burst[i]
        burst[i] = c.model_copy(
            update={"high": c.high + 4.0, "low": c.low - 4.0, "close": c.close + 2.0}
        )
    eff, fast_mult = volatility_stop_scale(burst, atr)
    assert eff > atr
    assert fast_mult > calm_mult


def test_manual_only_never_signals():
    strat = ManualOnlyStrategy()
    bars = _bars()
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=datetime(2026, 7, 20, 14, 5, tzinfo=timezone.utc),
    )
    assert strat.evaluate(tick) is None
