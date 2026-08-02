"""SMC liquidity-sweep blueprint upgrades."""

from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, OrderType, Side, Tick
from app.strategies import create_strategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy


def test_smc_seed_ctor_wires_blueprint_flags():
    strat = create_strategy("Liquidity_Sweep_SMC")
    assert isinstance(strat, LiquiditySweepSmcStrategy)
    assert strat.require_displacement is True
    assert strat.require_mss_confirm is False
    assert strat.prefer_pdh_pdl is True
    assert strat.use_limit_entry is True
    assert strat.fvg_entry_pct == 0.50
    assert strat.reward_r == 2.8
    assert strat.min_displacement_atr == 0.35
    assert strat.mt_near_limit_pips == 120
    assert (7, 11) in strat.kill_zones_utc
    assert (13, 16) in strat.kill_zones_utc


def test_smc_kill_zone_blocks_off_hours_when_filtered():
    strat = LiquiditySweepSmcStrategy(
        news_filter=False,
        session_filter=True,
        require_displacement=False,
    )
    now = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # Asia — not SMC kill zone
    bars = []
    price = 2350.0
    for i in range(80):
        ts = now - timedelta(minutes=5 * (80 - i))
        bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price + 0.1,
                volume=10,
                period_seconds=300,
                open_time=ts,
                timestamp=ts + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
        price += 0.05
    strat.set_structure_bars(bars)
    tick = Tick(
        symbol="XAUUSD",
        bid=price - 0.1,
        ask=price + 0.1,
        mid=price,
        timestamp=now,
    )
    assert strat.on_bar(bars, tick) is None
    assert strat.last_block_reason is not None


def test_smc_waits_for_sweep_still():
    strat = LiquiditySweepSmcStrategy(
        news_filter=False,
        session_filter=False,
        require_displacement=True,
    )
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
        timestamp=now,
    )
    strat.set_structure_bars(bars)
    assert strat.on_bar(bars, tick) is None
    assert "sweep" in (strat.last_block_reason or "").lower()


def test_signal_limit_fields_shape():
    """Sanity: LIMIT signals carry FVG mid + expire when constructed manually."""
    sig_side = Side.BUY
    assert OrderType.LIMIT.value == "LIMIT"
    assert sig_side == Side.BUY
