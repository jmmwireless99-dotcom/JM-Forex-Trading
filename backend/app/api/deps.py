from app.core.config import Settings, get_settings
from app.engine.trading_engine import TradingEngine

_engine: TradingEngine | None = None


def get_engine() -> TradingEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = TradingEngine(settings)
    return _engine


def reset_engine(settings: Settings | None = None) -> TradingEngine:
    global _engine
    _engine = TradingEngine(settings or get_settings())
    return _engine