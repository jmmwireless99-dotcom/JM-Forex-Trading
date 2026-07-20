from datetime import datetime, timezone

import pytest

from app.api.deps import reset_engine
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import Tick


def _tick(ts: datetime, price: float = 2350.0) -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=ts,
    )


@pytest.mark.asyncio
async def test_session_change_transfers_strategy():
    engine = TradingEngine(
        Settings(
            auto_strategy=True,
            default_strategy="auto_gold",
            news_filter=False,
            strategy_stick_seconds=900,
            entry_cooldown_seconds=0,
        )
    )
    engine.auto_enabled = True
    # Seed warm prices so regime can resolve
    for i in range(80):
        engine._strategies["gold_confluence"].feed(
            _tick(datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc), 2350 + (i % 3) * 0.05)
        )

    asia = _tick(datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc))
    await engine._apply_auto_router(asia)
    assert engine._last_session_slot == "asia"
    assert engine.active_name == "asia_range_scalp"

    london = _tick(datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc))
    # Uptrend prices so London may pick ATR or confluence — either is fine,
    # but must leave asia_range_scalp.
    for i in range(40):
        engine._strategies["gold_confluence"].feed(
            _tick(london.timestamp, 2300 + i * 0.8)
        )
    await engine._apply_auto_router(london)
    assert engine._last_session_slot == "london"
    assert engine.active_name != "asia_range_scalp"
    assert engine.active_name in {"gold_confluence", "gold_atr_trend", "gold_sr_scalp"}
    assert engine._last_transfer_note is not None
    assert "london" in (engine._last_transfer_note or "")

    # Back to Asia — must return to asia_range_scalp park
    asia2 = _tick(datetime(2026, 7, 22, 2, 30, tzinfo=timezone.utc))
    await engine._apply_auto_router(asia2)
    assert engine._last_session_slot == "asia"
    assert engine.active_name == "asia_range_scalp"

    await engine.stop()
    reset_engine(Settings())
