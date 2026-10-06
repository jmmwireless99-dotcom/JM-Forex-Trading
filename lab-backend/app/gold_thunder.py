"""JM Thunder GOLD Scalper V1.0.0 helpers (mirrors JM_THUNDER_GOLD_SCALPER.mq5)."""

from __future__ import annotations


def v640_hour_allowed(direction: int, hour: int, *, enabled: bool = True) -> bool:
    if not enabled:
        return True
    hour %= 24
    if hour == 4 and direction < 0:
        return True
    if hour == 5:
        return True
    if hour == 8:
        return True
    if hour == 11 and direction < 0:
        return True
    if hour == 12 and direction < 0:
        return True
    if hour == 17 and direction > 0:
        return True
    if hour == 19 and direction > 0:
        return True
    if hour == 21 and direction < 0:
        return True
    if hour == 22 and direction > 0:
        return True
    return False


def pht_hour(server_hour: int, broker_utc: int = 3) -> int:
    return (server_hour + (8 - broker_utc) + 24) % 24


def m5_bias(
    fast: float,
    slow: float,
    adx: float,
    m5atr: float,
    *,
    min_adx: float = 16.0,
    use_chop: bool = True,
    min_gap: float = 0.06,
    weak_adx: float = 20.0,
) -> tuple[int, float]:
    if m5atr <= 0:
        return 0, 0.0
    gap = abs(fast - slow) / m5atr
    if adx < min_adx:
        return 0, gap
    if use_chop and gap < min_gap and adx < weak_adx:
        return 0, gap
    if fast > slow:
        return 1, gap
    if fast < slow:
        return -1, gap
    return 0, gap


def is_small_candle(
    body_ratio: float,
    range_atr: float,
    *,
    body_max: float = 0.45,
    range_min: float = 0.15,
    range_max: float = 0.80,
) -> bool:
    return range_min <= range_atr <= range_max and body_ratio <= body_max


def thunder_swing_break(
    direction: int,
    last_high: float,
    last_low: float,
    last_open: float,
    last_close: float,
    prior_highs: list[float],
    prior_lows: list[float],
    *,
    buffer: float = 0.0,
) -> bool:
    if direction == 0 or not prior_highs or not prior_lows:
        return False
    if direction > 0:
        swing = max(prior_highs)
        return last_high > swing + buffer and last_close > last_open
    swing = min(prior_lows)
    return last_low < swing - buffer and last_close < last_open


def flow_score(
    bias: int,
    flow: int,
    adx: float,
    gap: float,
    rsi: float,
    body_ratio: float,
    range_atr: float,
    *,
    weak_adx: float = 20.0,
    min_gap: float = 0.06,
) -> int:
    score = 0
    if flow == bias:
        score += 1
    if adx >= weak_adx:
        score += 1
    if gap >= min_gap:
        score += 1
    if 0.25 <= range_atr <= 0.65:
        score += 1
    if bias > 0 and 48.0 <= rsi <= 64.0:
        score += 1
    if bias < 0 and 36.0 <= rsi <= 52.0:
        score += 1
    if 0.12 <= body_ratio <= 0.40:
        score += 1
    return score


def nfp_blocked(
    day_of_week: int,
    day: int,
    hour: int,
    *,
    enabled: bool = True,
    start_hour: int = 14,
    end_hour: int = 17,
) -> bool:
    if not enabled:
        return False
    if day_of_week != 5:
        return False
    if day > 7:
        return False
    return start_hour <= hour < end_hour


def select_tp_usd(
    adx: float,
    gap: float,
    lots: float,
    *,
    base: float = 30.0,
    strong: float = 45.0,
    adx_need: float = 32.0,
    gap_need: float = 0.55,
    ref_lot: float = 0.01,
    dynamic: bool = True,
) -> float:
    tp = base
    if dynamic and adx >= adx_need and gap >= gap_need:
        tp = strong
    if ref_lot <= 0:
        return tp
    return tp * (lots / ref_lot)
