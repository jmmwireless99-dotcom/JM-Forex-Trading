"""BTCUSD MT4 bridge routing — prefer MT BTC ticks; fan-out when EA is on BTC."""

from app.brokers.remote_mt_store import remote_push
from app.engine.trading_engine import TradingEngine
from app.models.domain import Side, Signal


def test_is_btc_symbol_helper():
    assert TradingEngine._is_btc_symbol("BTCUSD")
    assert TradingEngine._is_btc_symbol("btcusdt")
    assert TradingEngine._is_btc_symbol("Bitcoin")
    assert not TradingEngine._is_btc_symbol("XAUUSD")
    assert not TradingEngine._is_btc_symbol("EURUSD")


def test_mt_bridge_supports_btc_from_agent_push():
    remote_push(
        status_csv="ok,1000,1000,0,2026.07.24 12:00:00,893283499,1,\n",
        ticks_csv="BTCUSD,95000.10,95005.40,2026.07.24 12:00:00\n",
        symbol="BTCUSD",
        platform="mt4",
        agent_host="test-pc",
    )
    eng = object.__new__(TradingEngine)
    assert eng._mt_bridge_live_symbol("mt4") == "BTCUSD"
    assert eng._mt_bridge_supports_symbol("mt4", "BTCUSD")
    assert not eng._mt_bridge_supports_symbol("mt4", "XAUUSD")


def test_mt_bridge_supports_gold_from_agent_push():
    remote_push(
        status_csv="ok,1000,1000,0,2026.07.24 12:00:00,893283499,1,\n",
        ticks_csv="XAUUSD,4050.10,4050.40,2026.07.24 12:00:00\n",
        symbol="XAUUSD",
        platform="mt4",
        agent_host="test-pc",
    )
    eng = object.__new__(TradingEngine)
    assert eng._mt_bridge_supports_symbol("mt4", "XAUUSD")
    assert not eng._mt_bridge_supports_symbol("mt4", "BTCUSD")


def test_btc_signal_shape():
    sig = Signal(
        strategy="BTC_EMA_RSI_Scalp",
        symbol="BTCUSD",
        side=Side.BUY,
        strength=0.9,
        reason="test",
        stop_loss=94000.0,
        take_profit=97200.0,
    )
    assert TradingEngine._is_btc_symbol(sig.symbol)
