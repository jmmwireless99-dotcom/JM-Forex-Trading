"""GOLD session + V6.77 scalper signal helpers (mirrors JM_GOLD_Session_Signal_v1.mq5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


PH = timezone(timedelta(hours=8))

# Defaults: PH clock, end exclusive. Wrap if start > end.
ASIA_START, ASIA_END = 8, 16
LONDON_START, LONDON_END = 15, 0
NY_START, NY_END = 20, 5
OVERLAP_START, OVERLAP_END = 20, 0


def in_hour_range(hour: int, start: int, end: int) -> bool:
    hour = hour % 24
    start %= 24
    end %= 24
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def ph_from_utc(utc: datetime) -> datetime:
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    return utc.astimezone(PH)


def format_ph_hour_label(hour: int) -> str:
    h = hour % 24
    h12 = h % 12 or 12
    return f"{h12}{'PM' if h >= 12 else 'AM'}"


def format_ph_clock(ph: datetime) -> str:
    h12 = ph.hour % 12 or 12
    ampm = "PM" if ph.hour >= 12 else "AM"
    return f"{h12}:{ph.minute:02d} {ampm}"


def session_band(hour: int) -> str:
    """Color band key for the hour label on the candle."""
    name = classify_ph_session(hour)
    return {
        "LONDON-NY OVERLAP": "overlap",
        "NEW YORK": "ny",
        "LONDON": "london",
        "ASIAN/TOKYO": "asia",
        "OFF-HOURS": "daily",
    }[name]


def classify_ph_session(
    hour: int,
    *,
    asia=(ASIA_START, ASIA_END),
    london=(LONDON_START, LONDON_END),
    ny=(NY_START, NY_END),
    overlap=(OVERLAP_START, OVERLAP_END),
) -> str:
    """Overlap wins, then NY, London, Asia, else OFF-HOURS."""
    if in_hour_range(hour, overlap[0], overlap[1]):
        return "LONDON-NY OVERLAP"
    if in_hour_range(hour, ny[0], ny[1]):
        return "NEW YORK"
    if in_hour_range(hour, london[0], london[1]):
        return "LONDON"
    if in_hour_range(hour, asia[0], asia[1]):
        return "ASIAN/TOKYO"
    return "OFF-HOURS"


def side_from_ema(close: float, ema: float) -> str | None:
    if close > ema:
        return "BUY"
    if close < ema:
        return "SELL"
    return None


def rsi_momentum(rsi: float, rsi_prev: float, side: str, *, buy_min=45.0, buy_max=70.0, sell_min=30.0, sell_max=55.0) -> bool:
    if side == "BUY":
        return buy_min <= rsi <= buy_max and rsi > rsi_prev
    if side == "SELL":
        return sell_min <= rsi <= sell_max and rsi < rsi_prev
    return False


def bb_bounce(
    side: str,
    high: float,
    low: float,
    close: float,
    open_: float,
    bb_upper: float,
    bb_lower: float,
) -> bool:
    """True bounce: one band only, close back inside on the bounce side of midline.

    A dump/rally bar that spans both bands is not a bounce (sold the lows / bought the highs).
    """
    if bb_upper <= bb_lower:
        return False
    hit_low = low <= bb_lower
    hit_up = high >= bb_upper
    if hit_low and hit_up:
        return False
    rng = high - low
    if rng <= 0:
        return False
    mid = 0.5 * (bb_upper + bb_lower)
    if side == "BUY":
        if not hit_low:
            return False
        if close <= bb_lower or close <= open_:
            return False
        if close > mid:
            return False
        return (high - close) / rng >= 0.28
    if side == "SELL":
        if not hit_up:
            return False
        if close >= bb_upper or close >= open_:
            return False
        if close < mid:
            return False
        return (close - low) / rng >= 0.28
    return False


def candle_ok(side: str, open_: float, close: float) -> bool:
    if side == "BUY":
        return close > open_
    if side == "SELL":
        return close < open_
    return False


def htf_side(fast: float, slow: float) -> str | None:
    if fast > slow:
        return "BUY"
    if fast < slow:
        return "SELL"
    return None


def signal_passes(
    side: str,
    *,
    ema_side: str | None,
    rsi_ok: bool,
    bb_ok: bool,
    candle: bool,
    h4: str | None,
    h1: str | None,
    m15: str | None,
    require_ema=True,
    require_rsi=True,
    require_bb=True,
    require_candle=True,
    require_h4=False,
    require_h1=True,
    require_m15=False,
    easy_arrows=False,
) -> bool:
    if easy_arrows:
        require_rsi = False
        require_bb = False
        require_h1 = False
        require_m15 = False
        require_h4 = False
    checks = []
    if require_ema:
        checks.append(ema_side == side)
    if require_rsi:
        checks.append(rsi_ok)
    if require_bb:
        checks.append(bb_ok)
    if require_candle:
        checks.append(candle)
    if require_h4:
        checks.append(h4 == side)
    if require_h1:
        checks.append(h1 == side)
    if require_m15:
        checks.append(m15 == side)
    return bool(checks) and all(checks)


def reason_pack(
    *,
    session: str,
    ph_clock: str,
    side: str,
    entry: float,
    h4: str | None,
    h1: str | None,
    m15: str | None,
    ema_side: str | None,
    rsi: float,
    bb_tag: str,
    candle: str,
) -> str:
    return (
        f"SIDE={side}|PH={ph_clock}|SESSION={session}|ENTRY={entry:.2f}"
        f"|H4={h4 or 'FLAT'}|H1={h1 or 'FLAT'}|M15={m15 or 'FLAT'}"
        f"|EMA={ema_side or 'FLAT'}|RSI={rsi:.1f}|BB={bb_tag}|CANDLE={candle}"
    )


def signal_card(
    *,
    side: str,
    ph_clock: str,
    session: str,
    h1: str | None,
    m15: str | None = None,
    m30: str | None = None,
    entry: float,
) -> str:
    arrow = "BUY ▲" if side == "BUY" else "SELL ▼"
    htf = m30 or m15
    label = "M30 TREND" if m30 is not None else "M15 MOMENTUM"
    return (
        f"{arrow}\n"
        f"PH TIME: {ph_clock}\n"
        f"SESSION: {session}\n"
        f"H1 TREND: {h1 or 'FLAT'}\n"
        f"{label}: {htf or 'FLAT'}\n"
        f"ENTRY: {entry:.2f}"
    )


def v640_profit_hour_allowed(direction: int, hour: int) -> bool:
    """Server-hour gate from JM GOLD V6.77. +1 BUY, -1 SELL."""
    hour = hour % 24
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


def scalper_block_reason(
    bias: int,
    adx: float,
    gap: float,
    *,
    block_mid_adx: bool = True,
    mid_from: float = 25.0,
    mid_to: float = 35.0,
    v641: bool = True,
    v641_from: float = 20.0,
    v641_to: float = 25.0,
    v642: bool = True,
    v642_from: float = 0.50,
    v642_to: float = 1.00,
    v643: bool = True,
    v643_from: float = 0.75,
    v643_to: float = 1.00,
    block_buy_weak_gap: bool = True,
    buy_weak_gap: float = 0.25,
) -> str | None:
    if block_mid_adx and mid_from <= adx < mid_to:
        return "MID_ADX"
    if v641 and bias < 0 and v641_from <= adx < v641_to:
        return "SELL_ADX_20_25"
    if v642 and bias > 0 and v642_from <= gap < v642_to:
        return "BUY_GAP_050_100"
    if v643 and bias < 0 and v643_from <= gap < v643_to:
        return "SELL_GAP_075_100"
    if block_buy_weak_gap and bias > 0 and gap < buy_weak_gap:
        return "BUY_WEAK_EMA_GAP"
    return None


def is_small_candle(
    body_ratio: float,
    range_atr: float,
    *,
    max_body: float = 0.45,
    min_range: float = 0.15,
    max_range: float = 0.80,
) -> bool:
    return min_range <= range_atr <= max_range and body_ratio <= max_body


def closed_m1_breakout(
    bias: int,
    small_high: float,
    small_low: float,
    brk_high: float,
    brk_low: float,
    atr: float,
    buffer_atr: float = 0.05,
) -> bool:
    if atr <= 0:
        return False
    buf = atr * buffer_atr
    if bias > 0:
        return brk_high > small_high + buf
    if bias < 0:
        return brk_low < small_low - buf
    return False


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
    if bias > 0:
        if 48.0 <= rsi <= 64.0:
            score += 1
    else:
        if 36.0 <= rsi <= 52.0:
            score += 1
    if 0.12 <= body_ratio <= 0.40:
        score += 1
    return score


def rsi_entry_ok(
    bias: int,
    rsi: float,
    *,
    buy_min: float = 46.0,
    buy_max: float = 68.0,
    sell_min: float = 32.0,
    sell_max: float = 54.0,
) -> bool:
    if bias > 0:
        return buy_min <= rsi <= buy_max
    if bias < 0:
        return sell_min <= rsi <= sell_max
    return False


def scalper_signal_passes(
    bias: int,
    *,
    adx: float,
    gap: float,
    flow: int,
    rsi: float,
    body_ratio: float,
    range_atr: float,
    small_ok: bool,
    breakout_ok: bool,
    h1: str | None,
    m30: str | None,
    h4: str | None,
    server_hour: int,
    require_m1_flow: bool = True,
    use_flow_score: bool = True,
    min_score: int = 3,
    use_v640: bool = True,
    require_h1: bool = True,
    require_m30: bool = True,
    require_h4: bool = False,
) -> bool:
    if bias == 0:
        return False
    if scalper_block_reason(bias, adx, gap) is not None:
        return False
    if not small_ok:
        return False
    if require_m1_flow and flow != bias:
        return False
    score = flow_score(bias, flow, adx, gap, rsi, body_ratio, range_atr)
    if use_flow_score and score < min_score:
        return False
    if not rsi_entry_ok(bias, rsi):
        return False
    if use_v640 and not v640_profit_hour_allowed(bias, server_hour):
        return False
    side = "BUY" if bias > 0 else "SELL"
    if require_h1 and h1 != side:
        return False
    if require_m30 and m30 != side:
        return False
    if require_h4 and h4 != side:
        return False
    if not breakout_ok:
        return False
    return True


def scalper_reason_pack(
    *,
    session: str,
    ph_clock: str,
    side: str,
    entry: float,
    h4: str | None,
    h1: str | None,
    m30: str | None,
    m5: str | None,
    adx: float,
    gap: float,
    rsi: float,
    score: int,
    v640: bool = True,
) -> str:
    return (
        f"SIDE={side}|PH={ph_clock}|SESSION={session}|ENTRY={entry:.2f}"
        f"|H4={h4 or 'FLAT'}|H1={h1 or 'FLAT'}|M30={m30 or 'FLAT'}|M5={m5 or 'FLAT'}"
        f"|ADX={adx:.1f}|GAP={gap:.3f}|RSI={rsi:.1f}|SCORE={score}"
        f"|V640={'ON' if v640 else 'off'}|SMALL+BREAK"
    )
