from app.strategies.base import Strategy
from app.strategies.ema_rsi_scalp import EmaRsiScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy
from app.strategies.manual_only import ManualOnlyStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    ManualOnlyStrategy.name: ManualOnlyStrategy,
    EmaRsiScalpStrategy.name: EmaRsiScalpStrategy,
    LiquiditySweepSmcStrategy.name: LiquiditySweepSmcStrategy,
}

# Aliases for UI / older labels
_ALIASES = {
    "ema_rsi_scalp": EmaRsiScalpStrategy.name,
    "ema_rsi": EmaRsiScalpStrategy.name,
    "smc": LiquiditySweepSmcStrategy.name,
    "liquidity_sweep_smc": LiquiditySweepSmcStrategy.name,
}

META_STRATEGIES: list[str] = []


def list_strategy_names() -> list[str]:
    return META_STRATEGIES + list(STRATEGY_REGISTRY.keys())


def create_strategy(name: str, **kwargs) -> Strategy:
    kwargs.pop("managed_by_auto", None)
    key = (name or "").strip() or ManualOnlyStrategy.name
    if key.startswith("auto_gold"):
        key = ManualOnlyStrategy.name
    key = _ALIASES.get(key.lower(), key)
    cls = STRATEGY_REGISTRY.get(key)
    if cls is None:
        cls = ManualOnlyStrategy
        key = ManualOnlyStrategy.name
    lookback = kwargs.get("lookback")
    if lookback is not None:
        return cls(lookback=lookback)
    return cls()


__all__ = [
    "STRATEGY_REGISTRY",
    "META_STRATEGIES",
    "ManualOnlyStrategy",
    "EmaRsiScalpStrategy",
    "LiquiditySweepSmcStrategy",
    "Strategy",
    "create_strategy",
    "list_strategy_names",
]
