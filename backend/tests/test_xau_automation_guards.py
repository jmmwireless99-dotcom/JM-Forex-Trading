"""Guards for XAUUSD automation + strategy geometry bugs."""

from app.engine.trading_engine import TradingEngine


def test_gold_family_tick_matches_xauusd_strategy():
    eng = object.__new__(TradingEngine)
    assert eng._tick_matches_trade_symbol("XAUUSD", "XAUUSD")
    assert eng._tick_matches_trade_symbol("XAUUSDm", "XAUUSD")
    assert eng._tick_matches_trade_symbol("GOLD", "XAUUSD")
    assert not eng._tick_matches_trade_symbol("EURUSD", "XAUUSD")


def test_strategy_feed_gating_gold_only():
    eng = object.__new__(TradingEngine)

    class _Gold:
        name = "EMA_RSI_Scalp"

    assert eng._strategy_accepts_tick_symbol(_Gold(), "XAUUSDm")
    assert not eng._strategy_accepts_tick_symbol(_Gold(), "EURUSD")
