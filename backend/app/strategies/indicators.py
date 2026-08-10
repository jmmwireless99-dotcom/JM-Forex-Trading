from __future__ import annotations

from datetime import date, datetime

from app.models.domain import Candle


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    result = sum(values[:period]) / period
    for price in values[period:]:
        result = price * k + result * (1 - k)
    return result


def atr(values: list[float], period: int = 14) -> float | None:
    """Close-to-close ATR proxy (works on tick/mid series)."""
    if len(values) < period + 1:
        return None
    ranges = [abs(values[i] - values[i - 1]) for i in range(-period, 0)]
    return sum(ranges) / period


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def adx(values: list[float], period: int = 14) -> float | None:
    """Simplified ADX from a mid-price series (trend strength 0–100)."""
    need = period * 2 + 1
    if len(values) < need:
        return None

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for i in range(1, len(values)):
        up = values[i] - values[i - 1]
        down = values[i - 1] - values[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(abs(up))

    if len(trs) < period * 2:
        return None

    def wilder(series: list[float], n: int) -> list[float]:
        seed = sum(series[:n])
        out = [seed]
        for value in series[n:]:
            seed = seed - (seed / n) + value
            out.append(seed)
        return out

    atr_s = wilder(trs, period)
    plus_s = wilder(plus_dm, period)
    minus_s = wilder(minus_dm, period)
    dx_vals: list[float] = []
    for a, p, m in zip(atr_s, plus_s, minus_s):
        if a == 0:
            dx_vals.append(0.0)
            continue
        plus_di = 100 * (p / a)
        minus_di = 100 * (m / a)
        denom = plus_di + minus_di
        dx_vals.append(0.0 if denom == 0 else abs(plus_di - minus_di) / denom * 100)

    if len(dx_vals) < period:
        return None
    return sum(dx_vals[-period:]) / period


def ema_crossover(
    closes: list[float], fast: int, slow: int
) -> str | None:
    """Return 'bull' when fast crosses above slow, 'bear' when below."""
    if len(closes) < slow + 2:
        return None
    prev_fast = ema(closes[:-1], fast)
    prev_slow = ema(closes[:-1], slow)
    cur_fast = ema(closes, fast)
    cur_slow = ema(closes, slow)
    if None in (prev_fast, prev_slow, cur_fast, cur_slow):
        return None
    if prev_fast <= prev_slow and cur_fast > cur_slow:
        return "bull"
    if prev_fast >= prev_slow and cur_fast < cur_slow:
        return "bear"
    return None


def _candle_session_date(candle: Candle) -> date:
    ts = candle.open_time or candle.timestamp
    if isinstance(ts, datetime):
        return ts.date()
    return ts


def vwap(candles: list[Candle], session_date: date | None = None) -> float | None:
    """Session VWAP from UTC midnight using typical price × volume."""
    if not candles:
        return None
    session_date = session_date or _candle_session_date(candles[-1])
    cum_pv = 0.0
    cum_vol = 0.0
    for candle in candles:
        if _candle_session_date(candle) != session_date:
            continue
        typical = (candle.high + candle.low + candle.close) / 3
        vol = max(float(candle.volume or 1.0), 1.0)
        cum_pv += typical * vol
        cum_vol += vol
    if cum_vol <= 0:
        return None
    return cum_pv / cum_vol
