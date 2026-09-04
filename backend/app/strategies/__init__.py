from app.ai.aiml_strategy import AIMLStrategy
from app.strategies.base import Strategy
from app.strategies.ema_rsi_scalp import EmaRsiScalpStrategy
from app.strategies.ema_vwap_scalp import EmaVwapScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy
from app.strategies.manual_only import ManualOnlyStrategy
from app.strategies.news_breakout import NewsBreakoutStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    AIMLStrategy.name: AIMLStrategy,
    ManualOnlyStrategy.name: ManualOnlyStrategy,
    EmaRsiScalpStrategy.name: EmaRsiScalpStrategy,
    EmaVwapScalpStrategy.name: EmaVwapScalpStrategy,
    LiquiditySweepSmcStrategy.name: LiquiditySweepSmcStrategy,
    NewsBreakoutStrategy.name: NewsBreakoutStrategy,
}

# Aliases for UI / older labels
_ALIASES = {
    "ai_ml": AIMLStrategy.name,
    "aiml": AIMLStrategy.name,
    "ai-ml": AIMLStrategy.name,
    "machine_learning": AIMLStrategy.name,
    "ml": AIMLStrategy.name,
    "ema_rsi_scalp": EmaRsiScalpStrategy.name,
    "ema_rsi": EmaRsiScalpStrategy.name,
    "ema_vwap_scalp": EmaVwapScalpStrategy.name,
    "ema_vwap": EmaVwapScalpStrategy.name,
    "vwap_scalp": EmaVwapScalpStrategy.name,
    "smc": LiquiditySweepSmcStrategy.name,
    "liquidity_sweep_smc": LiquiditySweepSmcStrategy.name,
    "news_breakout": NewsBreakoutStrategy.name,
    "newsbreakout": NewsBreakoutStrategy.name,
}

META_STRATEGIES: list[str] = []


def list_strategy_names() -> list[str]:
    return META_STRATEGIES + list(STRATEGY_REGISTRY.keys())


def create_strategy(name: str, **kwargs) -> Strategy:
    kwargs.pop("managed_by_auto", None)
    key = (name or "").strip() or ManualOnlyStrategy.name
    if key.startswith("auto_gold"):
        key = AIMLStrategy.name
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
    "AIMLStrategy",
    "ManualOnlyStrategy",
    "EmaRsiScalpStrategy",
    "EmaVwapScalpStrategy",
    "LiquiditySweepSmcStrategy",
    "NewsBreakoutStrategy",
    "Strategy",
    "create_strategy",
    "list_strategy_names",
]
