from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Tick
from app.strategies.asia_range_scalp import AsiaRangeScalpStrategy
from app.strategies.session import SessionTier, classify_session


def test_asia_session_tier():
    ts = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # Tue 03:00 UTC = PH 11:00
    s = classify_session(ts)
    assert s.tier == SessionTier.ASIA
    assert s.label == "asia"


def test_asia_scalp_blocks_outside_desk():
    strat = AsiaRangeScalpStrategy(news_filter=False, asia_only=True)
    # 12:00 UTC = 20:00 PH — outside Asia desk
    outside = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    bars = []
    price = 2350.0
    for i in range(40):
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=price + 0.8,
                low=price - 0.8,
                close=price + 0.1,
                period_seconds=300,
                open_time=outside - timedelta(minutes=5 * (40 - i)),
                is_closed=True,
            )
        )
    tick = Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=outside,
    )
    assert strat.on_bar(bars, tick) is None
    assert any(c["name"] == "asia_session" and not c["ok"] for c in strat.last_checklist)
