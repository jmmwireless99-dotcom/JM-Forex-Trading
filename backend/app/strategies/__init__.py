from app.strategies.base import Strategy
from app.strategies.ema_crossover import EmaCrossoverStrategy
from app.strategies.gold_atr_trend import GoldAtrTrendStrategy
from app.strategies.gold_confluence import GoldConfluenceStrategy
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    GoldConfluenceStrategy.name: GoldConfluenceStrategy,
    GoldAtrTrendStrategy.name: GoldAtrTrendStrategy,
    EmaCrossoverStrategy.name: EmaCrossoverStrategy,
    RsiMeanReversionStrategy.name: RsiMeanReversionStrategy,
}


def create_strategy(name: str, **kwargs) -> Strategy:
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY)}")

    if name in {GoldConfluenceStrategy.name, GoldAtrTrendStrategy.name}:
        from app.core.config import get_settings

        settings = get_settings()
        kwargs.setdefault("session_filter", settings.session_filter)
        if name == GoldConfluenceStrategy.name:
            kwargs.setdefault("news_filter", settings.news_filter)
            kwargs.setdefault("prime_only", settings.prime_session_only)
    return cls(**kwargs)


__all__ = [
    "STRATEGY_REGISTRY",
    "EmaCrossoverStrategy",
    "GoldAtrTrendStrategy",
    "GoldConfluenceStrategy",
    "RsiMeanReversionStrategy",
    "Strategy",
    "create_strategy",
]