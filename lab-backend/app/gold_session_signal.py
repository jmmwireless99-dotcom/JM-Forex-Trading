"""GOLD session + signal helpers (mirrors JM_GOLD_Session_Signal_v1.mq5)."""

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


def format_ph_clock(ph: datetime) -> str:
    h12 = ph.hour % 12 or 12
    ampm = "PM" if ph.hour >= 12 else "AM"
    return f"{h12}:{ph.minute:02d} {ampm}"


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
    if side == "BUY":
        return low <= bb_lower and close > bb_lower and close > open_
    if side == "SELL":
        return high >= bb_upper and close < bb_upper and close < open_
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
) -> bool:
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
    m15: str | None,
    entry: float,
) -> str:
    arrow = "BUY ▲" if side == "BUY" else "SELL ▼"
    return (
        f"{arrow}\n"
        f"PH TIME: {ph_clock}\n"
        f"SESSION: {session}\n"
        f"H1 TREND: {h1 or 'FLAT'}\n"
        f"M15 MOMENTUM: {m15 or 'FLAT'}\n"
        f"ENTRY: {entry:.2f}"
    )
