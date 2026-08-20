from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class SessionTier(str, Enum):
    PRIME = "prime"  # London/NY overlap — best gold liquidity
    ALLOWED = "allowed"  # London afternoon or NY session
    ASIA = "asia"  # Asia scalp window (PH daytime)
    AVOID = "avoid"  # weekend / thin off-hours


@dataclass(frozen=True)
class SessionWindow:
    tier: SessionTier
    label: str
    reason: str


# Philippines desk — EMA_RSI runs through 8:30 PM Manila (UTC+8)
ASIA_PH_START_HOUR = 7
ASIA_PH_START_MINUTE = 0
ASIA_PH_END_HOUR = 20
ASIA_PH_END_MINUTE = 30  # inclusive → until 8:30 PM Manila

# UTC mirrors (Manila = UTC+8): 00:00 UTC = 8:00 AM PH … 12:30 UTC = 8:30 PM PH
EMA_RSI_UTC_END_HOUR = 12
EMA_RSI_UTC_END_MINUTE = 30
OVERLAP_UTC_END_HOUR = 18  # exclusive — 8:31 PM PH through 1:59 AM PH
NY_UTC_END_HOUR = 20  # exclusive — 2:00 AM through 3:59 AM PH


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


def ph_clock(utc: datetime) -> tuple[int, int]:
    """Return (hour, minute) in Manila time."""
    ph = utc.astimezone(timezone.utc) + timedelta(hours=8)
    return ph.hour, ph.minute


def _minutes(hour: int, minute: int = 0) -> int:
    return hour * 60 + minute


def utc_clock_minutes(ts: datetime) -> int:
    utc = ts.astimezone(timezone.utc)
    return _minutes(utc.hour, utc.minute)


def ph_clock_minutes(ts: datetime) -> int:
    h, m = ph_clock(ts)
    return _minutes(h, m)


def in_ema_rsi_ph_window(ts: datetime) -> bool:
    """EMA_RSI desk: Manila 7:00 AM – 8:30 PM inclusive."""
    start = _minutes(ASIA_PH_START_HOUR, ASIA_PH_START_MINUTE)
    end = _minutes(ASIA_PH_END_HOUR, ASIA_PH_END_MINUTE)
    return start <= ph_clock_minutes(ts) <= end


def in_ema_rsi_utc_window(ts: datetime) -> bool:
    """Full desk map: UTC 00:00 – 12:30 (= 8:00 AM – 8:30 PM Manila)."""
    return utc_clock_minutes(ts) <= _minutes(EMA_RSI_UTC_END_HOUR, EMA_RSI_UTC_END_MINUTE)


# Back-compat alias used by older imports
_ph_hour = ph_hour


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """Asia-only desk: EMA_RSI PH 07:00–20:30; flat outside (JM_ASIA_DESK_ONLY)."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    if in_ema_rsi_ph_window(ts):
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "EMA_RSI desk (PH 7:00AM–8:30PM) — M5 EMA + RSI scalp",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside EMA_RSI desk — next window PH 7:00AM–8:30PM",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full desk map aligned with strategy clocks (UTC).

    Asia / EMA_RSI  00:00–12:30 UTC  (PH 8:00 AM – 8:30 PM)
    Overlap / SMC   12:31–17:59 UTC  (PH 8:31 PM – 1:59 AM)
    New York / VWAP 18:00–19:59 UTC  (PH 2:00 AM – 3:59 AM)
    Off-hours       20:00–23:59 UTC  (PH 4:00 AM – 7:59 AM)
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    mins = utc_clock_minutes(ts)

    if mins <= _minutes(EMA_RSI_UTC_END_HOUR, EMA_RSI_UTC_END_MINUTE):
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "EMA_RSI session (PH 8:00AM–8:30PM) — M5 EMA + RSI scalp",
        )
    if mins < _minutes(OVERLAP_UTC_END_HOUR, 0):
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "London/NY overlap (PH 8:31PM–2:00AM) — SMC liquidity window",
        )
    if mins < _minutes(NY_UTC_END_HOUR, 0):
        return SessionWindow(
            SessionTier.ALLOWED,
            "new_york",
            "New York session (PH 2:00AM–4:00AM) — EMA_VWAP continuation",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "off_hours",
        "Off-hours (PH 4:00AM–8:00AM) — spreads widen, skip new entries",
    )


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — full hybrid by default; Asia-only if configured."""
    from app.core.config import get_settings

    if get_settings().asia_desk_only:
        return classify_asia_desk(ts)
    return classify_full_sessions(ts)


def session_allows_entry(ts: datetime, *, prime_only: bool = False) -> bool:
    tier = classify_session(ts).tier
    if prime_only:
        return tier == SessionTier.PRIME
    return tier in {SessionTier.PRIME, SessionTier.ALLOWED}


def session_allows_asia_scalp(ts: datetime) -> bool:
    return classify_session(ts).tier == SessionTier.ASIA


def next_session_hint(ts: datetime) -> dict:
    """What comes after the current slot — strategy recommendation for planning.

    Looks up to 72h ahead so Friday night / weekend still arms Monday Asia.
    """
    utc = ts.astimezone(timezone.utc)
    current = classify_session(utc)
    for add in range(1, 72 * 60 + 1):
        probe = utc + timedelta(minutes=add)
        nxt = classify_session(probe)
        if nxt.label != current.label and nxt.tier != SessionTier.AVOID:
            probe_utc = probe.astimezone(timezone.utc)
            return {
                "from_session": current.label,
                "session": nxt.label,
                "tier": nxt.tier.value,
                "hour_utc": probe_utc.hour,
                "minute_utc": probe_utc.minute,
                "strategy": _recommended_for_label(nxt.label, probe_utc.hour),
                "reason": _recommend_reason(nxt.label),
            }
    return {
        "from_session": current.label,
        "session": None,
        "tier": "avoid",
        "strategy": "AI_ML",
        "reason": "No nearer session — keep AI_ML armed",
    }


_SESSION_STRATEGY = {
    "asia": "AI_ML",
    "london_ny_overlap": "AI_ML",
    "new_york": "AI_ML",
}

_SESSION_CHILD = {
    "asia": "EMA_RSI_Scalp",
    "london_ny_overlap": "Liquidity_Sweep_SMC",
    "new_york": "EMA_VWAP_Scalp",
}


def _recommended_for_label(label: str, hour_utc: int) -> str | None:
    return _SESSION_STRATEGY.get(label)


def _recommend_reason(label: str) -> str:
    pick = _SESSION_STRATEGY.get(label)
    child = _SESSION_CHILD.get(label)
    if pick and child:
        return f"Next slot {label} → {pick}/{child}"
    if pick:
        return f"Next slot {label} → {pick}"
    return f"Next slot {label} — stand aside"
