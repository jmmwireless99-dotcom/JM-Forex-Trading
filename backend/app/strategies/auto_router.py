"""Minimal auto router stub — clean slate (no strategy schedule).

Returns stand-aside until new strategies are registered and wired.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.strategies.session import SessionTier, classify_session, next_session_hint


class Regime(str, Enum):
    TREND = "trend"
    PULLBACK = "pullback"
    RANGE = "range"
    VOLATILE = "volatile"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AutoDecision:
    allow_trading: bool
    strategy: str | None
    regime: Regime
    slot: str
    day: str
    weekday: int
    hour_utc: int
    session_tier: str
    reason: str
    adx: float | None = None
    atr: float | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["regime"] = self.regime.value
        return data


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class AutoStrategyRouter:
    """Placeholder router — no auto strategy picks until rebuilt."""

    name = "auto_gold"

    def __init__(self, *, news_filter: bool = True, **_: object) -> None:
        self.news_filter = news_filter
        self.last_decision: AutoDecision | None = None

    def decide(self, ts: datetime, prices: list[float]) -> AutoDecision:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        decision = AutoDecision(
            False,
            None,
            Regime.BLOCKED,
            session.label,
            day,
            utc.weekday(),
            utc.hour,
            session.tier.value,
            "Clean slate — no auto strategies loaded (manual trade only)",
        )
        self.last_decision = decision
        return decision

    def session_default(self, ts: datetime) -> dict:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        nxt = next_session_hint(utc)
        return {
            "session": session.label,
            "tier": session.tier.value,
            "day": DAY_NAMES[utc.weekday()],
            "hour_utc": utc.hour,
            "strategy": None,
            "mode": "stand_aside",
            "recommended": False,
            "next_session": nxt,
            "reason": "Clean slate — waiting for new strategy",
        }

    def recommend(self, ts: datetime, prices: list[float]) -> dict:
        base = self.session_default(ts)
        decision = self.decide(ts, prices)
        return {
            **base,
            "regime": decision.regime.value,
            "allow_trading": False,
            "strategy": None,
            "active_pick": None,
            "stand_aside": True,
            "reason": decision.reason,
            "adx": decision.adx,
            "atr": decision.atr,
            "transfer_to": None,
        }

    def schedule_table(self) -> list[dict]:
        return [
            {
                "days": "—",
                "utc": "—",
                "slot": "Clean slate",
                "strategies": "No auto strategies — build the next one",
            }
        ]
