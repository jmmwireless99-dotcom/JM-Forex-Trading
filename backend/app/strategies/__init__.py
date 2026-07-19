from app.strategies.base import Strategy
from app.strategies.ema_crossover import EmaCrossoverStrategy
from app.strategies.gold_atr_trend import GoldAtrTrendStrategy
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    GoldAtrTrendStrategy.name: GoldAtrTrendStrategy,
    EmaCrossoverStrategy.name: EmaCrossoverStrategy,
    RsiMeanReversionStrategy.name: RsiMeanReversionStrategy,
}


def create_strategy(name: str, **kwargs) -> Strategy:
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY)}")
    if name == GoldAtrTrendStrategy.name:
        from app.core.config import get_settings

        settings = get_settings()
        kwargs.setdefault("session_filter", settings.session_filter)
    return cls(**kwargs)


__all__ = [
    "STRATEGY_REGISTRY",
    "EmaCrossoverStrategy",
    "GoldAtrTrendStrategy",
    "RsiMeanReversionStrategy",
    "Strategy",
    "create_strategy",
]