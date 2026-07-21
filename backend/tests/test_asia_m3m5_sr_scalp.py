from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Tick
from app.strategies.asia_m3m5_sr_scalp import AsiaM3M5SrScalpStrategy
from app.strategies.auto_router import AutoStrategyRouter
from app.strategies.session import SessionTier, classify_session


def _bars(n: int, *, start: datetime, period: int, base: float = 2350.0) -> list[Candle]:
    bars: list[Candle] = []
    price = base
    for i in range(n):
        wave = ((i % 10) - 5) * 0.35
        o = price
        c = price + wave * 0.1
        h = max(o, c) + 0.6 + (0.8 if i % 10 == 2 else 0.0)
        l = min(o, c) - 0.6 - (0.8 if i % 10 == 7 else 0.0)
        price = c
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=h,
                low=l,
                close=c,
                period_seconds=period,
                open_time=start - timedelta(seconds=period * (n - i)),
                is_closed=True,
            )
        )
    return bars


def test_asia_window_ph_7_to_5():
    # 08:00 UTC = 16:00 PH → still Asia
    assert classify_session(datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)).tier == SessionTier.ASIA
    # 09:00 UTC = 17:00 PH → London (Asia ended)
    assert classify_session(datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)).label == "london"


def test_auto_router_picks_asia_m5_now():
    router = AutoStrategyRouter(news_filter=False)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    prices = [2350.0 + ((i % 4) - 1.5) * 0.05 for i in range(120)]
    d = router.decide(ts, prices)
    assert d.allow_trading is True
    assert d.strategy == "asia_m5_sr_scalp"


def test_strategy_blocks_after_5pm_ph():
    strat = AsiaM3M5SrScalpStrategy(news_filter=False, asia_only=True)
    # 10:00 UTC = 18:00 PH — outside 7–5
    ts = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    m5 = _bars(80, start=ts, period=300)
    m3 = _bars(80, start=ts, period=180)
    strat.set_structure_bars(m5)
    tick = Tick(
        symbol="XAUUSD",
        bid=m3[-1].close - 0.05,
        ask=m3[-1].close + 0.05,
        mid=m3[-1].close,
        timestamp=ts,
    )
    assert strat.on_bar(m3, tick) is None
    assert any(c["name"] == "asia_session" and not c["ok"] for c in strat.last_checklist)


def test_strategy_accepts_asia_morning():
    strat = AsiaM3M5SrScalpStrategy(news_filter=False, asia_only=True)
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # PH 11:00
    m5 = _bars(80, start=ts, period=300)
    m3 = _bars(80, start=ts, period=180)
    strat.set_structure_bars(m5)
    tick = Tick(
        symbol="XAUUSD",
        bid=m3[-1].close - 0.05,
        ask=m3[-1].close + 0.05,
        mid=m3[-1].close,
        timestamp=ts,
    )
    strat.on_bar(m3, tick)
    assert any(c["name"] == "asia_session" and c["ok"] for c in strat.last_checklist)
    assert strat.last_range is not None
    assert strat.last_range.get("entry") == "M3"
