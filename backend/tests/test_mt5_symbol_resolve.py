"""MT5 symbol resolution for remote bridge."""

from app.brokers.mt_bridge import _resolve_mt_symbol, resolve_mt_bridge
from app.core.config import Settings


def test_mt5_bridge_prefers_gold_symbol_over_mt4_default():
    settings = Settings(
        execution_mode="paper",
        mt4_symbol="XAUUSD",
        mt_symbol="GOLD#",
        mt5_bridge_dir="/tmp/bridge",
        mt_remote_bridge=True,
    )
    assert _resolve_mt_symbol(settings, mode="paper") == "GOLD#"
    bridge, platform = resolve_mt_bridge(settings)
    assert bridge is not None
    assert bridge.mt_symbol == "GOLD#"
    assert platform == "mt5"


def test_mt4_mode_uses_mt4_symbol():
    settings = Settings(
        execution_mode="mt4",
        mt4_symbol="XAUUSDm",
        mt_symbol="GOLD#",
        mt4_bridge_dir="/tmp/bridge",
    )
    assert _resolve_mt_symbol(settings, mode="mt4") == "XAUUSDm"
