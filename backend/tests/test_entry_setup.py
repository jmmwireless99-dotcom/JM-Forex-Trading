from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.gold_confluence import GoldConfluenceStrategy
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
    assert levels.reward_r >= 1.5


def test_confluence_waits_for_checklist():
    strat = GoldConfluenceStrategy(news_filter=False, session_filter=False, min_atr=0.2, min_adx=1.0)
    bars = _bars()
    tick = Tick(
        symbol="XAUUSD",
        bid=bars[-1].close - 0.1,
        ask=bars[-1].close + 0.1,
        mid=bars[-1].close,
        timestamp=datetime(2026, 7, 20, 14, 5, tzinfo=timezone.utc),
    )
    # evaluate() disabled on ticks
    assert strat.evaluate(tick) is None
    # on_bar may or may not fire depending on confirm candle — must not crash
    signal = strat.on_bar(bars, tick)
    assert signal is None or signal.stop_loss is not None
    assert isinstance(strat.last_checklist, list)
