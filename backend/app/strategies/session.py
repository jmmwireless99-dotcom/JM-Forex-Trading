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


# Asia M3/M5 scalp desk — Philippines local hours
ASIA_PH_START = 7
ASIA_PH_END = 20  # exclusive → active PH 7:00AM–7:59PM (flat from 8:00PM)


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


# Back-compat alias used by older imports
_ph_hour = ph_hour


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """Asia-only desk: scalp PH 07:00–19:59; flat outside (JM_ASIA_DESK_ONLY)."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    ph = ph_hour(utc)
    if ASIA_PH_START <= ph < ASIA_PH_END:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia scalp desk (PH 7:00AM–8:00PM) — M5 Support/Resistance",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside Asia desk hours — next window PH 7:00AM–8:00PM",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full desk map aligned with strategy clocks (UTC).

    Asia PH 7:00AM–8:00PM (UTC 23 + 00:00–11:59) — EMA_RSI
    London 07:00–12:59 — stand aside (Judas removed)
    Overlap 13:00–17:59 — SMC
    New York 18:00–19:59 — EMA_VWAP
    Off-hours / weekend — stand aside
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    hour = utc.hour
    ph = ph_hour(utc)

    if ASIA_PH_START <= ph < ASIA_PH_END:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia session (PH 7:00AM–8:00PM) — EMA_RSI + Asia range box",
        )
    if 7 <= hour < 13:
        return SessionWindow(
            SessionTier.AVOID,
            "london",
            "London session (UTC 07:00–12:59) — stand aside",
        )
    if 13 <= hour < 18:
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "London/NY overlap — best XAUUSD liquidity (SMC window)",
        )
    if 18 <= hour < 20:
        return SessionWindow(
            SessionTier.ALLOWED,
            "new_york",
            "New York session — USD-driven gold continuation",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "off_hours",
        "Off-hours — spreads widen, skip new entries",
    )


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — Asia-only by default; full hybrid if configured off."""
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
    for add in range(1, 73):
        probe = utc + timedelta(hours=add)
        nxt = classify_session(probe)
        if nxt.label != current.label and nxt.tier != SessionTier.AVOID:
            return {
                "from_session": current.label,
                "session": nxt.label,
                "tier": nxt.tier.value,
                "hour_utc": probe.hour,
                "strategy": _recommended_for_label(nxt.label, probe.hour),
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
