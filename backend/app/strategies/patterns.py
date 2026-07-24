"""Candlestick pattern helpers for XAUUSD scalping."""

from __future__ import annotations

from app.models.domain import Candle


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def _range(c: Candle) -> float:
    return max(c.high - c.low, 1e-9)


def bullish_engulfing(prev: Candle, cur: Candle) -> bool:
    if prev.close >= prev.open:
        return False
    if cur.close <= cur.open:
        return False
    return cur.open <= prev.close and cur.close >= prev.open and _body(cur) > _body(prev)


def bearish_engulfing(prev: Candle, cur: Candle) -> bool:
    if prev.close <= prev.open:
        return False
    if cur.close >= cur.open:
        return False
    return cur.open >= prev.close and cur.close <= prev.open and _body(cur) > _body(prev)


def bullish_pin_bar(c: Candle) -> bool:
    """Long lower wick, small body near top — rejection of lows."""
    r = _range(c)
    body = _body(c)
    lower = min(c.open, c.close) - c.low
    upper = c.high - max(c.open, c.close)
    return lower >= 0.55 * r and body <= 0.35 * r and upper <= 0.25 * r


def bearish_pin_bar(c: Candle) -> bool:
    """Long upper wick, small body near bottom — rejection of highs."""
    r = _range(c)
    body = _body(c)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    return upper >= 0.55 * r and body <= 0.35 * r and lower <= 0.25 * r
