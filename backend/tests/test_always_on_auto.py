"""Session auto-follow stays on when JM_AUTO_STRATEGY=true."""

from app.core.config import Settings
from app.engine.trading_engine import TradingEngine


def test_set_strategy_keeps_auto_on_when_configured():
    engine = TradingEngine(Settings(auto_strategy=True, default_strategy="manual_only"))
    assert engine.auto_enabled is True
    engine.set_strategy("EMA_RSI_Scalp")
    assert engine.auto_enabled is True
    assert engine.active_name == "EMA_RSI_Scalp"
    engine.set_strategy("manual_only")
    assert engine.auto_enabled is True


def test_set_strategy_can_disable_auto_when_not_configured():
    engine = TradingEngine(Settings(auto_strategy=False, default_strategy="manual_only"))
    assert engine.auto_enabled is False
    engine.set_strategy("EMA_RSI_Scalp")
    assert engine.auto_enabled is False
    assert engine.active_name == "EMA_RSI_Scalp"
