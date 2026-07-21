from app.strategies.asia_m3m5_sr_scalp import AsiaM3M5SrScalpStrategy
from app.strategies.asia_m5_sr_scalp import AsiaM5SrScalpStrategy
from app.strategies.asia_range_scalp import AsiaRangeScalpStrategy
from app.strategies.asia_sr_scalp import AsiaSrScalpStrategy
from app.strategies.auto_router import AutoStrategyRouter
from app.strategies.base import Strategy
from app.strategies.ema_crossover import EmaCrossoverStrategy
from app.strategies.gold_atr_trend import GoldAtrTrendStrategy
from app.strategies.gold_confluence import GoldConfluenceStrategy
from app.strategies.gold_sr_scalp import GoldSrScalpStrategy
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    GoldConfluenceStrategy.name: GoldConfluenceStrategy,
    GoldAtrTrendStrategy.name: GoldAtrTrendStrategy,
    GoldSrScalpStrategy.name: GoldSrScalpStrategy,
    AsiaM5SrScalpStrategy.name: AsiaM5SrScalpStrategy,
    AsiaM3M5SrScalpStrategy.name: AsiaM3M5SrScalpStrategy,
    AsiaSrScalpStrategy.name: AsiaSrScalpStrategy,
    AsiaRangeScalpStrategy.name: AsiaRangeScalpStrategy,
    EmaCrossoverStrategy.name: EmaCrossoverStrategy,
    RsiMeanReversionStrategy.name: RsiMeanReversionStrategy,
}

# Virtual / meta strategies exposed in the UI
META_STRATEGIES = ["auto_gold"]


def list_strategy_names() -> list[str]:
    return META_STRATEGIES + list(STRATEGY_REGISTRY.keys())


def create_strategy(name: str, **kwargs) -> Strategy:
    if name == "auto_gold":
        # Seed with confluence; engine owns the router switches.
        name = GoldConfluenceStrategy.name

    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown strategy: {name}. Available: {list_strategy_names()}"
        )

    # Engine flag — not a constructor arg on every strategy.
    managed_by_auto = bool(kwargs.pop("managed_by_auto", False))

    if name in {
        GoldConfluenceStrategy.name,
        GoldAtrTrendStrategy.name,
        GoldSrScalpStrategy.name,
    }:
        from app.core.config import get_settings

        settings = get_settings()
        # When auto router manages sessions/news, disable per-strategy filters
        # to avoid double-blocking (router already decided).
        if managed_by_auto:
            kwargs.setdefault("session_filter", False)
            if name in {GoldConfluenceStrategy.name, GoldSrScalpStrategy.name}:
                kwargs.setdefault("news_filter", False)
            if name == GoldConfluenceStrategy.name:
                kwargs.setdefault("prime_only", False)
        else:
            kwargs.setdefault("session_filter", settings.session_filter)
            if name == GoldConfluenceStrategy.name:
                kwargs.setdefault("news_filter", settings.news_filter)
                kwargs.setdefault("prime_only", settings.prime_session_only)
            if name == GoldSrScalpStrategy.name:
                kwargs.setdefault("news_filter", settings.news_filter)
    if name in {
        AsiaRangeScalpStrategy.name,
        AsiaSrScalpStrategy.name,
        AsiaM5SrScalpStrategy.name,
        AsiaM3M5SrScalpStrategy.name,
    } and managed_by_auto:
        # Router already gated Asia + news; strategy keeps asia_only for safety.
        kwargs.setdefault("news_filter", False)
    return cls(**kwargs)


__all__ = [
    "STRATEGY_REGISTRY",
    "META_STRATEGIES",
    "AsiaM3M5SrScalpStrategy",
    "AsiaM5SrScalpStrategy",
    "AsiaRangeScalpStrategy",
    "AsiaSrScalpStrategy",
    "AutoStrategyRouter",
    "EmaCrossoverStrategy",
    "GoldAtrTrendStrategy",
    "GoldConfluenceStrategy",
    "GoldSrScalpStrategy",
    "RsiMeanReversionStrategy",
    "Strategy",
    "create_strategy",
    "list_strategy_names",
]
