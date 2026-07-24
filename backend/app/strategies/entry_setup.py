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
    swing_lookback: int = 3,
    atr_pad: float = 0.35,
    min_stop_atr: float = 1.2,
    reward_r: float = 1.8,
    min_tp_atr: float = 2.5,
) -> Levels:
    """SL beyond recent swing + ATR pad; TP at least reward_r × risk."""
    window = candles[-swing_lookback:] if len(candles) >= swing_lookback else candles
    if side == Side.BUY:
        swing = min(c.low for c in window)
        raw_sl = swing - atr_pad * atr
        min_sl = entry - min_stop_atr * atr
        sl = min(raw_sl, min_sl)
        risk = max(entry - sl, min_stop_atr * atr * 0.5)
        sl = entry - risk
        tp_dist = max(reward_r * risk, min_tp_atr * atr)
        tp = entry + tp_dist
    else:
        swing = max(c.high for c in window)
        raw_sl = swing + atr_pad * atr
        max_sl = entry + min_stop_atr * atr
        sl = max(raw_sl, max_sl)
        risk = max(sl - entry, min_stop_atr * atr * 0.5)
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
