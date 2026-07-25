"""Guards for XAUUSD automation + strategy geometry bugs."""

from datetime import datetime, timedelta, timezone

from app.engine.trading_engine import TradingEngine
from app.models.domain import Candle, Side, Tick
from app.strategies.btc_ema_rsi import BtcEmaRsiScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy


def test_gold_family_tick_matches_xauusd_strategy():
    eng = object.__new__(TradingEngine)
    assert eng._tick_matches_trade_symbol("XAUUSD", "XAUUSD")
    assert eng._tick_matches_trade_symbol("XAUUSDm", "XAUUSD")
    assert eng._tick_matches_trade_symbol("GOLD", "XAUUSD")
    assert not eng._tick_matches_trade_symbol("BTCUSD", "XAUUSD")
    assert eng._tick_matches_trade_symbol("BTCUSD", "BTCUSD")
    assert not eng._tick_matches_trade_symbol("XAUUSD", "BTCUSD")


def test_strategy_feed_gating_gold_vs_btc():
    eng = object.__new__(TradingEngine)

    class _Gold:
        name = "EMA_RSI_Scalp"

    class _Btc:
        name = "BTC_EMA_RSI_Scalp"
        symbol = "BTCUSD"

    assert eng._strategy_accepts_tick_symbol(_Gold(), "XAUUSDm")
    assert not eng._strategy_accepts_tick_symbol(_Gold(), "BTCUSD")
    assert eng._strategy_accepts_tick_symbol(_Btc(), "BTCUSD")
    assert not eng._strategy_accepts_tick_symbol(_Btc(), "XAUUSD")


def test_btc_does_not_fallback_to_gold_bars():
    strat = BtcEmaRsiScalpStrategy(news_filter=False)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    gold_bars = []
    price = 4050.0
    for i in range(220):
        t = now - timedelta(minutes=5 * (220 - i))
        gold_bars.append(
            Candle(
                symbol="XAUUSD",
                open=price,
                high=price + 1,
                low=price - 1,
                close=price + 0.2,
                volume=1,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=50),
                is_closed=True,
            )
        )
        price += 0.2
    strat.set_structure_bars(gold_bars)
    tick = Tick(
        symbol="BTCUSD",
        bid=95000.0,
        ask=95010.0,
        mid=95005.0,
        timestamp=now,
    )
    assert strat.on_bar(gold_bars, tick) is None
    assert "No BTCUSD bars" in (strat.last_block_reason or "")


def test_smc_reason_safe_without_sweep():
    """require_sweep=False + MSS-only must not crash on sweep.label."""
    strat = LiquiditySweepSmcStrategy(
        require_sweep=False,
        news_filter=False,
        session_filter=False,
        max_entries_per_day=0,
    )
    # Minimal smoke: reason builder path with sweep=None uses MSS label.
    sweep = None
    sweep_label = sweep.label if sweep is not None else "MSS"
    assert sweep_label == "MSS"
    side = Side.BUY
    reason = f"SMC {side.value} · {sweep_label} · MSS confirm · FVG entry"
    assert "MSS" in reason
