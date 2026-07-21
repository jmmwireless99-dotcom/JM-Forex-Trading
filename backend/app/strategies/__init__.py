from app.strategies.base import Strategy
from app.strategies.manual_only import ManualOnlyStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    ManualOnlyStrategy.name: ManualOnlyStrategy,
}

# No auto desk until new strategies are added.
META_STRATEGIES: list[str] = []


def list_strategy_names() -> list[str]:
    return META_STRATEGIES + list(STRATEGY_REGISTRY.keys())


def create_strategy(name: str, **kwargs) -> Strategy:
    kwargs.pop("managed_by_auto", None)
    key = (name or "").strip() or ManualOnlyStrategy.name
    if key.startswith("auto_gold"):
        key = ManualOnlyStrategy.name
    cls = STRATEGY_REGISTRY.get(key, ManualOnlyStrategy)
    # Only pass lookback if provided — avoid unexpected kwargs on stub.
    lookback = kwargs.get("lookback")
    if lookback is not None:
        return cls(lookback=lookback)
    return cls()


__all__ = [
    "STRATEGY_REGISTRY",
    "META_STRATEGIES",
    "ManualOnlyStrategy",
    "Strategy",
    "create_strategy",
    "list_strategy_names",
]
