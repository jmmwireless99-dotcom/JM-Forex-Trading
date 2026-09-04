"""Asia desk SL/TP — vol-adaptive structure stops (entry + in-trade refresh)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.domain import Candle, Side
from app.strategies.entry_setup import (
    Levels,
    adaptive_vol_stop_scale,
    structure_levels,
    true_atr,
)


def asia_vol_scale(
    candles: list[Candle],
    atr: float,
    settings: Settings | None = None,
) -> tuple[float, float]:
    settings = settings or get_settings()
    if not settings.asia_vol_adaptive_stops:
        return atr, 1.0
    return adaptive_vol_stop_scale(
        candles,
        atr,
        mult_calm=settings.asia_vol_mult_calm,
        mult_normal=1.0,
        mult_fast=settings.asia_vol_mult_max,
    )


def compute_asia_levels(
    side: Side,
    *,
    entry: float,
    candles: list[Candle],
    atr: float,
    reward_r: float = 2.0,
    settings: Settings | None = None,
) -> Levels:
    """ATR structure SL/TP with bidirectional vol scaling for Asia desk."""
    settings = settings or get_settings()
    effective_atr, vol_mult = asia_vol_scale(candles, atr, settings)
    pad_eff = settings.asia_structure_atr_pad * (0.85 + 0.15 * vol_mult)
    return structure_levels(
        side,
        entry=entry,
        candles=candles,
        atr=effective_atr,
        swing_lookback=3,
        atr_pad=pad_eff,
        reward_r=reward_r,
        min_stop_atr=settings.asia_min_stop_atr * vol_mult,
        min_tp_atr=settings.asia_min_tp_atr * vol_mult,
    )


def apply_sl_tp_scale(
    side: Side,
    *,
    entry: float,
    stop_loss: float,
    take_profit: float,
    scale: float,
) -> tuple[float, float]:
    """Manual desk multiplier on top of vol-adaptive base levels."""
    scale = max(0.5, min(2.0, scale))
    sl_dist = abs(entry - stop_loss)
    tp_dist = abs(take_profit - entry)
    sl_dist *= scale
    tp_dist *= scale
    if side == Side.BUY:
        return round(entry - sl_dist, 2), round(entry + tp_dist, 2)
    return round(entry + sl_dist, 2), round(entry - tp_dist, 2)


def refresh_asia_position_stops(
    side: Side,
    *,
    entry: float,
    candles: list[Candle],
    atr: float | None = None,
    sl_tp_scale: float = 1.0,
    reward_r: float = 2.0,
    settings: Settings | None = None,
) -> Levels | None:
    """Recalculate Asia SL/TP from entry + live M5 tape (in-trade auto-adjust)."""
    atr_v = atr if atr is not None else true_atr(candles, 14)
    if atr_v is None or atr_v <= 0 or not candles:
        return None
    base = compute_asia_levels(
        side,
        entry=entry,
        candles=candles,
        atr=atr_v,
        reward_r=reward_r,
        settings=settings,
    )
    if abs(sl_tp_scale - 1.0) < 1e-6:
        return base
    sl, tp = apply_sl_tp_scale(
        side,
        entry=entry,
        stop_loss=base.stop_loss,
        take_profit=base.take_profit,
        scale=sl_tp_scale,
    )
    risk = abs(entry - sl)
    tp_dist = abs(tp - entry)
    return Levels(
        stop_loss=sl,
        take_profit=tp,
        risk=round(risk, 2),
        reward_r=round(tp_dist / risk, 2) if risk else base.reward_r,
    )


def stops_materially_changed(
    *,
    stop_loss: float | None,
    take_profit: float | None,
    new_sl: float,
    new_tp: float,
    min_delta: float = 0.05,
) -> bool:
    if stop_loss is None or take_profit is None:
        return True
    return (
        abs(stop_loss - new_sl) >= min_delta or abs(take_profit - new_tp) >= min_delta
    )
