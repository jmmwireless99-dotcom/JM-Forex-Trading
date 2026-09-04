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


# PH desk windows (local time = UTC+8)
ASIA_PH_START = 7
ASIA_PH_END = 20  # exclusive → PH 7:00AM–7:59PM

SMC_PH_START = 20  # PH 8:00PM
SMC_PH_END = 2  # exclusive → through 1:59AM (wraps midnight)

EARLY_EMA_PH_START = 2
EARLY_EMA_PH_END = 7  # exclusive → PH 2:00AM–6:59AM


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


# Back-compat alias used by older imports
_ph_hour = ph_hour


def in_smc_ph_window(ph: int) -> bool:
    """PH 8:00PM–1:59AM — crosses midnight."""
    return ph >= SMC_PH_START or ph < SMC_PH_END


def in_early_ema_ph_window(ph: int) -> bool:
    """PH 2:00AM–6:59AM."""
    return EARLY_EMA_PH_START <= ph < EARLY_EMA_PH_END


def in_asia_ph_window(ph: int) -> bool:
    """PH 7:00AM–7:59PM."""
    return ASIA_PH_START <= ph < ASIA_PH_END


def is_ph_night(utc: datetime) -> bool:
    """PH gabi desk — 8:00PM–6:59AM (SMC + early EMA, not Asia daytime)."""
    ph = ph_hour(utc)
    return ph >= SMC_PH_START or ph < EARLY_EMA_PH_END


def is_ph_evening_news_window(utc: datetime) -> bool:
    """PH 7:00PM–6:59AM — allows 1hr pre-news before 8PM for ~8:30PM US prints."""
    ph = ph_hour(utc)
    return ph >= 19 or ph < EARLY_EMA_PH_END


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """PH desk: Asia 7AM–8PM · SMC 8PM–2AM · EMA_RSI 2AM–7AM."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    ph = ph_hour(utc)
    if in_asia_ph_window(ph):
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia desk (PH 7:00AM–8:00PM) — EMA_RSI scalp",
        )
    if in_smc_ph_window(ph):
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "SMC desk (PH 8:00PM–2:00AM) — Liquidity Sweep",
        )
    if in_early_ema_ph_window(ph):
        return SessionWindow(
            SessionTier.ASIA,
            "off_hours",
            "Early Asia desk (PH 2:00AM–7:00AM) — EMA_RSI scalp",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside desk hours",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full desk map — same PH windows when hybrid mode is off."""
    return classify_asia_desk(ts)


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — PH desk by default; same map if hybrid off."""
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
    "off_hours": "AI_ML",
}

_SESSION_CHILD = {
    "asia": "EMA_RSI_Scalp",
    "london_ny_overlap": "Liquidity_Sweep_SMC",
    "off_hours": "EMA_RSI_Scalp",
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
