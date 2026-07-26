from app.db.seed import seed_params
from app.strategies.base import Strategy
from app.strategies.ema_rsi_scalp import EmaRsiScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy
from app.strategies.london_judas_sweep import LondonJudasSweepStrategy
from app.strategies.manual_only import ManualOnlyStrategy
from app.strategies.trend_breakout_atr import TrendBreakoutAtrStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    ManualOnlyStrategy.name: ManualOnlyStrategy,
    EmaRsiScalpStrategy.name: EmaRsiScalpStrategy,
    LiquiditySweepSmcStrategy.name: LiquiditySweepSmcStrategy,
    LondonJudasSweepStrategy.name: LondonJudasSweepStrategy,
    TrendBreakoutAtrStrategy.name: TrendBreakoutAtrStrategy,
}

# Aliases for UI / older labels
_ALIASES = {
    "ema_rsi_scalp": EmaRsiScalpStrategy.name,
    "ema_rsi": EmaRsiScalpStrategy.name,
    "smc": LiquiditySweepSmcStrategy.name,
    "liquidity_sweep_smc": LiquiditySweepSmcStrategy.name,
    "london": LondonJudasSweepStrategy.name,
    "london_judas": LondonJudasSweepStrategy.name,
    "london_judas_sweep": LondonJudasSweepStrategy.name,
    "judas": LondonJudasSweepStrategy.name,
    "trend_breakout": TrendBreakoutAtrStrategy.name,
    "trend_breakout_atr": TrendBreakoutAtrStrategy.name,
    "breakout": TrendBreakoutAtrStrategy.name,
    "donchian": TrendBreakoutAtrStrategy.name,
}

META_STRATEGIES: list[str] = []


def list_strategy_names() -> list[str]:
    return META_STRATEGIES + list(STRATEGY_REGISTRY.keys())


def _ctor_kwargs(name: str, overrides: dict) -> dict:
    """Map seed + caller kwargs onto each strategy constructor."""
    seed = seed_params(name)
    merged = {**seed, **{k: v for k, v in overrides.items() if v is not None}}
    out: dict = {}
    if "lookback" in overrides and overrides["lookback"] is not None:
        out["lookback"] = overrides["lookback"]

    if name == EmaRsiScalpStrategy.name:
        if "ema_trend" in merged:
            out["ema_trend"] = int(merged["ema_trend"])
        if "ema_fast" in merged:
            out["ema_fast"] = int(merged["ema_fast"])
        if "ema_slow" in merged:
            out["ema_slow"] = int(merged["ema_slow"])
        if "rsi_period" in merged:
            out["rsi_period"] = int(merged["rsi_period"])
        buy = merged.get("rsi_buy_zone") or merged.get("rsi_buy")
        sell = merged.get("rsi_sell_zone") or merged.get("rsi_sell")
        if buy and len(buy) == 2:
            out["rsi_buy"] = (float(buy[0]), float(buy[1]))
        if sell and len(sell) == 2:
            out["rsi_sell"] = (float(sell[0]), float(sell[1]))
        if "min_bars_between_signals" in merged:
            out["min_bars_between_signals"] = int(merged["min_bars_between_signals"])
        if "allow_soft_confirm" in merged:
            out["allow_soft_confirm"] = bool(merged["allow_soft_confirm"])
        if "reward_r" in merged:
            out["reward_r"] = float(merged["reward_r"])
        if "min_stop_atr" in merged:
            out["min_stop_atr"] = float(merged["min_stop_atr"])
        if "min_tp_atr" in merged:
            out["min_tp_atr"] = float(merged["min_tp_atr"])
        if "max_stop_atr" in merged:
            out["max_stop_atr"] = float(merged["max_stop_atr"])
    elif name == LiquiditySweepSmcStrategy.name:
        for flag in (
            "require_sweep",
            "require_zone_retest",
            "require_displacement",
            "prefer_pdh_pdl",
            "use_limit_entry",
        ):
            if flag in merged:
                out[flag] = bool(merged[flag])
        for key in (
            "reward_r",
            "min_stop_atr",
            "min_tp_atr",
            "max_stop_atr",
            "min_sweep_atr",
            "max_sweep_atr",
            "min_displacement_atr",
            "sl_buffer_atr",
            "min_sl_dollars",
            "fvg_entry_pct",
            "mt_near_limit_pips",
        ):
            if key in merged:
                out[key] = float(merged[key])
        if "max_entries_per_day" in merged:
            out["max_entries_per_day"] = int(merged["max_entries_per_day"])
        if "sweep_max_age_bars" in merged:
            out["sweep_max_age_bars"] = int(merged["sweep_max_age_bars"])
        if "kill_zones_utc" in merged and merged["kill_zones_utc"]:
            out["kill_zones_utc"] = tuple(
                tuple(int(x) for x in pair) for pair in merged["kill_zones_utc"]
            )
    elif name == LondonJudasSweepStrategy.name:
        for key in (
            "min_sweep_pips",
            "max_sweep_pips",
            "sl_buffer_pips",
            "max_spread_pips",
            "reward_r",
        ):
            if key in merged:
                out[key] = float(merged[key])
        if "mt_near_limit_pips" in merged:
            out["mt_near_limit_pips"] = float(merged["mt_near_limit_pips"])
    elif name == TrendBreakoutAtrStrategy.name:
        for key in (
            "channel_period",
            "ema_trend",
            "adx_period",
            "min_bars_between_signals",
        ):
            if key in merged:
                out[key] = int(merged[key])
        for key in (
            "min_adx",
            "min_break_atr",
            "reward_r",
            "min_stop_atr",
            "min_tp_atr",
            "max_stop_atr",
        ):
            if key in merged:
                out[key] = float(merged[key])
        if "kill_zones_utc" in merged and merged["kill_zones_utc"]:
            out["kill_zones_utc"] = tuple(
                tuple(int(x) for x in pair) for pair in merged["kill_zones_utc"]
            )
    return out


def create_strategy(name: str, **kwargs) -> Strategy:
    kwargs.pop("managed_by_auto", None)
    key = (name or "").strip() or ManualOnlyStrategy.name
    if key.startswith("auto_gold"):
        key = ManualOnlyStrategy.name
    # Retired crypto strategy — fall back to manual.
    if key.upper().startswith("BTC") or "BTC" in key.upper():
        key = ManualOnlyStrategy.name
    key = _ALIASES.get(key.lower(), key)
    cls = STRATEGY_REGISTRY.get(key)
    if cls is None:
        cls = ManualOnlyStrategy
        key = ManualOnlyStrategy.name
    if key == ManualOnlyStrategy.name:
        return cls()
    ctor = _ctor_kwargs(key, kwargs)
    return cls(**ctor)


__all__ = [
    "STRATEGY_REGISTRY",
    "META_STRATEGIES",
    "ManualOnlyStrategy",
    "EmaRsiScalpStrategy",
    "LiquiditySweepSmcStrategy",
    "LondonJudasSweepStrategy",
    "TrendBreakoutAtrStrategy",
    "Strategy",
    "create_strategy",
    "list_strategy_names",
]
