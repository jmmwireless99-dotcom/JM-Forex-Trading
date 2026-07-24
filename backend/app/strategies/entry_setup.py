"""Shared helpers for candle-based gold entries (structure SL / R-multiple TP)."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Candle, Side


@dataclass(frozen=True)
class Levels:
    stop_loss: float
    take_profit: float
    risk: float
    reward_r: float


def true_atr(candles: list[Candle], period: int = 14) -> float | None:
    """Wilder-style ATR from OHLC true range."""
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev), abs(c.low - prev))
        trs.append(tr)
    if len(trs) < period:
        return None
    # Simple ATR average of last `period` true ranges (stable enough for desk)
    return sum(trs[-period:]) / period


def structure_levels(
    side: Side,
    *,
    entry: float,
    candles: list[Candle],
    atr: float,
    swing_lookback: int = 8,
    atr_pad: float = 0.35,
    min_stop_atr: float = 1.2,
    max_stop_atr: float = 2.8,
    reward_r: float = 2.2,
    min_tp_atr: float = 2.5,
    anchor_sl: float | None = None,
) -> Levels:
    """SL beyond recent swing (+ optional liquidity/sweep anchor); TP at reward_r × risk.

    Correct analysis first: structure invalidation, then capped risk, then R-multiple TP.
    """
    lookback = max(3, swing_lookback)
    window = candles[-lookback:] if len(candles) >= lookback else candles
    atr = max(float(atr), 1e-6)
    min_risk = min_stop_atr * atr
    max_risk = max(max_stop_atr * atr, min_risk)

    if side == Side.BUY:
        swing = min(c.low for c in window)
        candidates = [swing - atr_pad * atr, entry - min_risk]
        if anchor_sl is not None:
            candidates.append(float(anchor_sl))
        sl = min(candidates)
        risk = entry - sl
        if risk < min_risk:
            risk = min_risk
            sl = entry - risk
        elif risk > max_risk:
            risk = max_risk
            sl = entry - risk
        tp_dist = max(reward_r * risk, min_tp_atr * atr)
        tp = entry + tp_dist
    else:
        swing = max(c.high for c in window)
        candidates = [swing + atr_pad * atr, entry + min_risk]
        if anchor_sl is not None:
            candidates.append(float(anchor_sl))
        sl = max(candidates)
        risk = sl - entry
        if risk < min_risk:
            risk = min_risk
            sl = entry + risk
        elif risk > max_risk:
            risk = max_risk
            sl = entry + risk
        tp_dist = max(reward_r * risk, min_tp_atr * atr)
        tp = entry - tp_dist

    return Levels(
        stop_loss=round(sl, 2),
        take_profit=round(tp, 2),
        risk=round(risk, 2),
        reward_r=round(tp_dist / risk, 2) if risk else reward_r,
    )


def bullish_confirm(candle: Candle) -> bool:
    return candle.close > candle.open and candle.close >= candle.low + 0.55 * (
        candle.high - candle.low + 1e-9
    )


def bearish_confirm(candle: Candle) -> bool:
    return candle.close < candle.open and candle.close <= candle.high - 0.55 * (
        candle.high - candle.low + 1e-9
    )


def recent_stretch_above(candles: list[Candle], level: float, lookback: int = 5) -> bool:
    for c in candles[-lookback:]:
        if c.high >= level:
            return True
    return False


def recent_stretch_below(candles: list[Candle], level: float, lookback: int = 5) -> bool:
    for c in candles[-lookback:]:
        if c.low <= level:
            return True
    return False


def pulled_into_zone(
    candles: list[Candle], *, mid: float, band: float, lookback: int = 4
) -> bool:
    """True if a recent low/high touched the value zone around mid."""
    for c in candles[-lookback:]:
        if abs(c.low - mid) <= band or abs(c.high - mid) <= band or abs(c.close - mid) <= band:
            return True
    return False
