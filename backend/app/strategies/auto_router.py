from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.strategies.indicators import adx, atr, ema
from app.strategies.news_calendar import check_news_blackout
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
    """Pick gold strategy automatically from day + session + market regime.

    Default full desk (JM_ASIA_DESK_ONLY=false) — entries on closed M5 only:
      Asia PH 7AM–7PM (UTC 23–11) → asia_sr_scalp (BEST Asia M5 S/R)
      Late London UTC 11–13       → gold_confluence (BEST next after Asia)
      Overlap UTC 13–16           → gold_atr_trend (BEST liquidity)
      NY UTC 16–20                → gold_atr_trend / confluence
      Range/chop London–NY        → gold_sr_scalp
      Fri 18+ / weekend / news    → stand aside

    JM_ASIA_DESK_ONLY=true keeps Asia-only flat after PH 7PM.
    """

    name = "auto_gold"

    def __init__(
        self,
        *,
        news_filter: bool = True,
        min_trend_adx: float = 28.0,
        min_trade_adx: float = 20.0,
        high_atr: float = 1.8,
    ) -> None:
        self.news_filter = news_filter
        self.min_trend_adx = min_trend_adx
        self.min_trade_adx = min_trade_adx
        self.high_atr = high_atr
        self.last_decision: AutoDecision | None = None

    def detect_regime(self, prices: list[float]) -> tuple[Regime, float | None, float | None]:
        vol = atr(prices, 14)
        strength = adx(prices, 14)
        fast = ema(prices, 21)
        slow = ema(prices, 55)
        if vol is None or strength is None or fast is None or slow is None:
            return Regime.RANGE, strength, vol

        if vol >= self.high_atr and strength >= self.min_trend_adx:
            return Regime.VOLATILE, strength, vol
        if strength >= self.min_trend_adx and abs(fast - slow) > 0.15 * vol:
            return Regime.TREND, strength, vol
        if strength >= self.min_trade_adx:
            return Regime.PULLBACK, strength, vol
        return Regime.RANGE, strength, vol

    def decide(self, ts: datetime, prices: list[float]) -> AutoDecision:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        hour = utc.hour
        regime, adx_v, atr_v = self.detect_regime(prices)

        # Weekend / off-hours hard block (Asia is handled below as scalp window)
        if session.tier == SessionTier.AVOID:
            decision = AutoDecision(
                False,
                None,
                Regime.BLOCKED,
                session.label,
                day,
                utc.weekday(),
                hour,
                session.tier.value,
                session.reason,
                adx_v,
                atr_v,
            )
            self.last_decision = decision
            return decision

        # Asia scalp desk — recommended: M5 Support/Resistance fade
        if session.tier == SessionTier.ASIA:
            if regime == Regime.VOLATILE:
                decision = AutoDecision(
                    False,
                    None,
                    Regime.BLOCKED,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    "Asia desk volatile — stand aside (spike risk)",
                    adx_v,
                    atr_v,
                )
            else:
                decision = AutoDecision(
                    True,
                    "asia_sr_scalp",
                    regime,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    "Asia recommended: M5 Support/Resistance scalp (asia_sr_scalp)",
                    adx_v,
                    atr_v,
                )
            self.last_decision = decision
            return decision

        # Friday late — avoid weekend gap risk (full-session map only)
        if utc.weekday() == 4 and hour >= 18:
            decision = AutoDecision(
                False,
                None,
                Regime.BLOCKED,
                "friday_late",
                day,
                utc.weekday(),
                hour,
                session.tier.value,
                "Friday after 18:00 UTC — no new gold trades (weekend gap risk)",
                adx_v,
                atr_v,
            )
            self.last_decision = decision
            return decision

        # News blackout
        if self.news_filter:
            news = check_news_blackout(utc)
            if news.blocked:
                decision = AutoDecision(
                    False,
                    None,
                    Regime.BLOCKED,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    news.reason,
                    adx_v,
                    atr_v,
                )
                self.last_decision = decision
                return decision

        strategy, reason = self._pick_strategy(session.label, session.tier, regime, hour)
        allow = strategy is not None
        decision = AutoDecision(
            allow,
            strategy,
            regime if allow else Regime.BLOCKED,
            session.label,
            day,
            utc.weekday(),
            hour,
            session.tier.value,
            reason,
            adx_v,
            atr_v,
        )
        self.last_decision = decision
        return decision

    def _pick_strategy(
        self,
        slot: str,
        tier: SessionTier,
        regime: Regime,
        hour: int,
    ) -> tuple[str | None, str]:
        # London/NY chop → S/R supply-demand scalp (Asia has its own range path).
        if regime == Regime.RANGE:
            return (
                "gold_sr_scalp",
                f"{slot}: range/chop — S/R supply-demand scalp",
            )

        if tier == SessionTier.PRIME:
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return (
                    "gold_atr_trend",
                    "Overlap + strong trend — ATR trend strategy",
                )
            # PULLBACK → S/R scalp
            return (
                "gold_sr_scalp",
                "Overlap pullback — S/R supply-demand scalp",
            )

        if slot == "london":
            if regime == Regime.TREND:
                return "gold_atr_trend", "London trend — gold_atr_trend"
            if regime == Regime.PULLBACK:
                return (
                    "gold_confluence",
                    "London recommended: gold_confluence (pullback after Asia)",
                )
            return "gold_sr_scalp", "London chop — gold_sr_scalp"

        if slot == "new_york":
            if hour >= 18:
                if regime in {Regime.TREND, Regime.VOLATILE}:
                    return "gold_confluence", "Late NY — confluence only if trend continues"
                if regime == Regime.PULLBACK:
                    return "gold_sr_scalp", "Late NY pullback — S/R supply-demand scalp"
                return None, "Late NY without trend — stand aside"
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return "gold_atr_trend", "NY continuation — ATR trend"
            return "gold_sr_scalp", "NY pullback — S/R supply-demand scalp"

        if regime == Regime.PULLBACK:
            return "gold_sr_scalp", "Default pullback — S/R supply-demand scalp"
        return "gold_confluence", "Default gold confluence"

    def session_default(self, ts: datetime) -> dict:
        """Recommended strategy from session clock alone (before regime refine)."""
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        hour = utc.hour
        nxt = next_session_hint(utc)

        if session.tier == SessionTier.AVOID or (utc.weekday() == 4 and hour >= 18):
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": None,
                "mode": "stand_aside",
                "recommended": False,
                "next_session": nxt,
                "reason": session.reason
                if session.tier == SessionTier.AVOID
                else "Friday after 18:00 UTC — no new gold trades",
            }
        if session.tier == SessionTier.ASIA:
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "asia_sr_scalp",
                "mode": "auto_transfer",
                "recommended": True,
                "next_session": nxt,
                "reason": (
                    "Asia BEST (PH 7AM–7PM): asia_sr_scalp — M5 Support/Resistance · "
                    f"Next: {nxt.get('strategy')} ({nxt.get('session')})"
                ),
            }
        if session.tier == SessionTier.PRIME:
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_atr_trend",
                "mode": "auto_transfer",
                "recommended": True,
                "next_session": nxt,
                "reason": (
                    "Overlap BEST: gold_atr_trend — prime liquidity "
                    "(fallback gold_sr_scalp on range/pullback)"
                ),
            }
        if session.label == "london":
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_confluence",
                "mode": "auto_transfer",
                "recommended": True,
                "next_session": nxt,
                "reason": (
                    "London BEST after Asia: gold_confluence — "
                    "ATR if trend · gold_sr_scalp if chop"
                ),
            }
        if session.label == "new_york":
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_atr_trend" if hour < 18 else "gold_confluence",
                "mode": "auto_transfer",
                "recommended": True,
                "next_session": nxt,
                "reason": "NY BEST: gold_atr_trend early · gold_confluence late",
            }
        return {
            "session": session.label,
            "tier": session.tier.value,
            "day": day,
            "hour_utc": hour,
            "strategy": "gold_confluence",
            "mode": "auto_transfer",
            "recommended": False,
            "next_session": nxt,
            "reason": "Default — gold_confluence",
        }

    def recommend(self, ts: datetime, prices: list[float]) -> dict:
        """Full recommendation: session default refined by live regime decision."""
        base = self.session_default(ts)
        decision = self.decide(ts, prices)
        return {
            **base,
            "regime": decision.regime.value,
            "allow_trading": decision.allow_trading,
            "strategy": decision.strategy if decision.allow_trading else base.get("strategy"),
            "active_pick": decision.strategy,
            "stand_aside": not decision.allow_trading,
            "reason": decision.reason,
            "adx": decision.adx,
            "atr": decision.atr,
            "next_session": base.get("next_session"),
            "transfer_to": (
                decision.strategy
                if decision.allow_trading and decision.strategy
                else base.get("strategy")
            ),
        }

    def schedule_table(self) -> list[dict]:
        """Human-readable weekly plan for the dashboard."""
        from app.core.config import get_settings

        if get_settings().asia_desk_only:
            return [
                {
                    "days": "Mon–Fri",
                    "utc": "23:00–11:00 (PH 7:00AM–7:00PM)",
                    "slot": "Asia scalp desk",
                    "strategies": (
                        "BEST: asia_sr_scalp — M5 Support/Resistance fade · "
                        "FLAT if volatile"
                    ),
                },
                {
                    "days": "Mon–Fri",
                    "utc": "after PH 7PM",
                    "slot": "Outside Asia desk",
                    "strategies": "NO new trades (asia_desk_only)",
                },
                {
                    "days": "Sat–Sun",
                    "utc": "weekend",
                    "slot": "Weekend",
                    "strategies": "NO new trades",
                },
                {
                    "days": "Any",
                    "utc": "NFP/CPI/FOMC window",
                    "slot": "News blackout",
                    "strategies": "NO new trades",
                },
            ]
        return [
            {
                "days": "Mon–Fri",
                "utc": "23:00–11:00 (PH 7AM–7PM)",
                "slot": "Asia",
                "strategies": "BEST: asia_sr_scalp — M5 Support/Resistance fade",
            },
            {
                "days": "Mon–Fri",
                "utc": "11:00–13:00 (after PH 7PM)",
                "slot": "Late London",
                "strategies": (
                    "BEST next: gold_confluence · gold_atr_trend if trend · "
                    "gold_sr_scalp if chop"
                ),
            },
            {
                "days": "Mon–Fri",
                "utc": "13:00–16:00",
                "slot": "London/NY overlap (PRIME)",
                "strategies": (
                    "BEST: gold_atr_trend · gold_sr_scalp on range/pullback"
                ),
            },
            {
                "days": "Mon–Thu",
                "utc": "16:00–20:00",
                "slot": "New York",
                "strategies": (
                    "BEST: gold_atr_trend · gold_confluence late · "
                    "gold_sr_scalp if chop"
                ),
            },
            {
                "days": "Fri",
                "utc": "18:00+",
                "slot": "Friday late",
                "strategies": "NO new trades",
            },
            {
                "days": "Sat–Sun / late",
                "utc": "weekend / off-hours",
                "slot": "Avoid",
                "strategies": "NO new trades",
            },
            {
                "days": "Any",
                "utc": "NFP/CPI/FOMC window",
                "slot": "News blackout",
                "strategies": "NO new trades",
            },
        ]
