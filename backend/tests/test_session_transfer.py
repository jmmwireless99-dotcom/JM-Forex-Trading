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
            asia_desk_only=True,
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
    assert engine.active_name == "asia_sr_scalp"

    # After PH 7PM (12:00 UTC = 20:00 PH) — desk closed
    closed = _tick(datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc))
    await engine._apply_auto_router(closed)
    assert engine._last_session_slot == "outside_asia_desk"
    assert engine._last_transfer_note is not None
    assert "outside_asia_desk" in (engine._last_transfer_note or "")

    # Next Asia morning — back to asia_sr_scalp park
    asia2 = _tick(datetime(2026, 7, 22, 2, 30, tzinfo=timezone.utc))
    await engine._apply_auto_router(asia2)
    assert engine._last_session_slot == "asia"
    assert engine.active_name == "asia_sr_scalp"

    await engine.stop()
    reset_engine(Settings())
