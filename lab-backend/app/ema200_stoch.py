"""EMA200 + Stochastic 5,3,3 gold scalp helpers (mirrors the MT5 EA)."""

from __future__ import annotations


def is_small_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    body_max: float = 0.55,
    min_range: float = 0.20,
) -> bool:
    span = high - low
    if span < min_range:
        return False
    body = abs(close - open_)
    return (body / span) <= body_max


def ema200_side(price: float, ema: float) -> str | None:
    if price > ema:
        return "BUY"
    if price < ema:
        return "SELL"
    return None


def stoch_buy_cross(
    k_prev: float,
    d_prev: float,
    k: float,
    d: float,
    *,
    os: float = 20.0,
) -> bool:
    return k_prev <= os and d_prev <= os and k > d and k > k_prev


def stoch_sell_cross(
    k_prev: float,
    d_prev: float,
    k: float,
    d: float,
    *,
    ob: float = 80.0,
) -> bool:
    return k_prev >= ob and d_prev >= ob and k < d and k < k_prev


def pullback_ok(dir: int, candles: list[dict], *, bars: int = 2, body_max: float = 0.55) -> bool:
    """candles[0] = newest. Pullback bars start at index 1 (previous closed is trigger)."""
    if len(candles) < bars + 1:
        return False
    for i in range(1, bars + 1):
        c = candles[i]
        if not is_small_candle(c["open"], c["high"], c["low"], c["close"], body_max=body_max):
            return False
        if dir > 0 and not (c["close"] < c["open"]):
            return False
        if dir < 0 and not (c["close"] > c["open"]):
            return False
    return True


def scale_out_volumes(start: float, *, min_lot: float = 0.01) -> tuple[float, float, float]:
    """Return (tp1_close, tp2_close, runner). Zeros if start too small to split."""
    if start < min_lot * 2 - 1e-9:
        return (0.0, 0.0, start)
    if start < min_lot * 3 - 1e-9:
        return (min_lot, 0.0, round(start - min_lot, 2))
    leg = min_lot
    rest = round(start - 2 * leg, 2)
    return (leg, leg, rest)


def nfp_friday_blocked(weekday: int, day: int, hour: int, start: int = 14, end: int = 17) -> bool:
    """weekday: Mon=0 … Fri=4. First Friday = day 1–7."""
    return weekday == 4 and day <= 7 and start <= hour < end


def favorable_price_move(side: str, entry: float, bid: float, ask: float) -> float:
    """Gold quote dollars in favor of the position (not account P/L)."""
    if side == "BUY":
        return bid - entry
    return entry - ask


def next_scale_action(
    move: float,
    *,
    tp1: float = 5.0,
    tp2: float = 10.0,
    tp3: float = 15.0,
    did_tp1: bool = False,
    did_tp2: bool = False,
    remaining_is_min_lot: bool = False,
) -> str:
    """Scale-out stage. Min-lot remainder cannot partial — close at the *next* target only."""
    if remaining_is_min_lot:
        if not did_tp1 and move >= tp1:
            return "CLOSE"
        if did_tp1 and not did_tp2 and move >= tp2:
            return "CLOSE"
        if did_tp2 and move >= tp3:
            return "CLOSE"
        return "HOLD"
    if not did_tp1 and move >= tp1:
        return "TP1"
    if did_tp1 and not did_tp2 and move >= tp2:
        return "TP2"
    if did_tp1 and move >= tp3:
        return "TP3"
    return "HOLD"
