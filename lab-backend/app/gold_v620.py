"""V6.20 result-based gates (TP30/SL15 journal). No new indicators."""

from __future__ import annotations


def h21_sell_blocked(side: str, hour: int, *, enabled: bool = True) -> bool:
    return enabled and side == "SELL" and hour == 21


def strong_trend_score_adj(
    adx: float,
    m5_atr: float,
    *,
    enabled: bool = True,
    adx_min: float = 35.0,
    atr_min: float = 8.0,
    adj: int = -1,
) -> int:
    if not enabled:
        return 0
    if adx >= adx_min and m5_atr >= atr_min:
        return adj
    return 0


def apply_required_score(base_need: int, adx: float, m5_atr: float, **kwargs) -> int:
    need = base_need + strong_trend_score_adj(adx, m5_atr, **kwargs)
    return max(1, need)
