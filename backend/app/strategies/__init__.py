from app.strategies.base import Strategy
from app.strategies.ema_crossover import EmaCrossoverStrategy
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    EmaCrossoverStrategy.name: EmaCrossoverStrategy,
    RsiMeanReversionStrategy.name: RsiMeanReversionStrategy,
}


def create_strategy(name: str) -> Strategy:
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY)}")
    return cls()


__all__ = [
    "STRATEGY_REGISTRY",
    "EmaCrossoverStrategy",
    "RsiMeanReversionStrategy",
    "Strategy",
    "create_strategy",
]