"""Seed parameters must drive live strategy constructors."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle
from app.strategies import create_strategy
from app.strategies.liquidity_sweep_smc import _asia_window_bars


def test_create_strategy_applies_seed_defaults():
    ema = create_strategy("EMA_RSI_Scalp")
    assert ema.rsi_buy == (38.0, 52.0)
    assert ema.rsi_sell == (48.0, 62.0)
    assert ema.min_bars_between_signals == 6
    assert ema.allow_soft_confirm is True
    assert ema.reward_r == 1.8

    smc = create_strategy("Liquidity_Sweep_SMC")
    assert smc.require_sweep is True
    assert smc.require_zone_retest is True

    judas = create_strategy("London_Judas_Sweep")
    assert judas.min_sweep_pips == 50.0
    assert judas.mt_near_limit_pips == 150.0
    assert judas.reward_r == 3.0


def test_smc_asia_box_matches_london_00_06():
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    bars: list[Candle] = []
    for i in range(24):
        t = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=30 * i)
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                timestamp=t,
                open_time=t,
                period_seconds=300,
                is_closed=True,
                volume=1,
            )
        )
    asia = _asia_window_bars(bars, now)
    assert asia
    assert all(c.timestamp.astimezone(timezone.utc).hour < 6 for c in asia)
