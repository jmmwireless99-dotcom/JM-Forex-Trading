"""Session-based strategy router for XAUUSD scalp desk."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.strategies.session import (
    SESSION_STRATEGY,
    SessionTier,
    classify_session,
    next_session_hint,
    schedule_table as session_schedule_table,
)


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
    """Maps session slots to best-fit strategies and transfer hints."""

    name = "auto_gold"

    def __init__(self, *, news_filter: bool = True, **_: object) -> None:
        self.news_filter = news_filter
        self.last_decision: AutoDecision | None = None
        # Single source of truth: FULL_SESSION_SLOTS in session.py (Mon–Fri always-on).
        self.session_map: dict[str, str | None] = {
            **{k: v for k, v in SESSION_STRATEGY.items()},
            "friday_late": None,
            "weekend": None,
            "outside_asia_desk": None,
        }

    def _pick(self, session_label: str) -> str | None:
        return self.session_map.get(session_label)

    def decide(self, ts: datetime, prices: list[float]) -> AutoDecision:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        pick = self._pick(session.label)
        allow = session.tier != SessionTier.AVOID and pick is not None
        reason = (
            f"Session {session.label}: auto-pick {pick}"
            if allow
            else f"Session {session.label}: stand aside"
        )
        decision = AutoDecision(
            allow,
            pick,
            Regime.RANGE if allow else Regime.BLOCKED,
            session.label,
            day,
            utc.weekday(),
            utc.hour,
            session.tier.value,
            reason,
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
            "strategy": self._pick(session.label),
            "mode": "session_follow",
            "recommended": self._pick(session.label) is not None,
            "next_session": nxt,
            "reason": f"Session-follow map for {session.label}",
        }

    def recommend(self, ts: datetime, prices: list[float]) -> dict:
        base = self.session_default(ts)
        decision = self.decide(ts, prices)
        return {
            **base,
            "regime": decision.regime.value,
            "allow_trading": decision.allow_trading,
            "strategy": decision.strategy,
            "active_pick": decision.strategy,
            "stand_aside": not decision.allow_trading,
            "reason": decision.reason,
            "adx": decision.adx,
            "atr": decision.atr,
            "transfer_to": decision.strategy,
        }

    def schedule_table(self) -> list[dict]:
        """Strategy + time-session table (UTC + PH) with hourly auto-transfer row."""
        return session_schedule_table()
