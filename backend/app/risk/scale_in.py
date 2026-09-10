"""Scale-in (up to 3 legs) — only for paper accounts with scale_in_mode=True."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.models.domain import OrderRequest, Position, PositionStatus, Side, Tick
from app.risk.manager import RiskDecision

if TYPE_CHECKING:
    from app.core.config import Settings


def pip_size(symbol: str) -> float:
    return 0.1 if (symbol or "").upper() == "XAUUSD" else 0.0001


def scale_in_step_pips_for_session(
    settings: Settings,
    ts: datetime | None = None,
) -> float:
    """Leg spacing for SCALE3 — wider at night (SMC) than Asia EMA desk."""
    from app.strategies.session import classify_session

    when = ts or datetime.now(timezone.utc)
    label = classify_session(when).label
    if label == "london_ny_overlap":
        return float(getattr(settings, "scale_in_step_pips_night", 125.0))
    if label in ("asia", "off_hours"):
        return float(getattr(settings, "scale_in_step_pips_asia", 75.0))
    return float(getattr(settings, "scale_in_step_pips", 75.0))


def scale_in_lots(balance: float, leg: int, settings: Settings) -> float:
    """Leg 1/2/3 → base×1, base×2, base×3 where base = floor(balance/1000)×0.01."""
    tier = max(1, int(balance // 1000))
    base = tier * float(getattr(settings, "scale_in_base_lot_per_1k", 0.01))
    leg_n = max(1, min(int(leg), int(getattr(settings, "scale_in_max_legs", 3))))
    return round(base * leg_n, 2)


def open_legs(
    positions: list[Position], *, symbol: str, side: Side
) -> list[Position]:
    legs = [
        p
        for p in positions
        if p.status == PositionStatus.OPEN
        and p.symbol == symbol
        and p.side == side
    ]
    legs.sort(key=lambda p: (p.leg_index or 1, p.opened_at))
    return legs


def setup_id_for_legs(legs: list[Position]) -> str | None:
    if not legs:
        return None
    for p in legs:
        if p.setup_id:
            return p.setup_id
    return legs[0].id[:12]


def price_depth_ok(
    *,
    side: Side,
    last_entry: float,
    current: float,
    step_pips: float,
    symbol: str,
) -> bool:
    step = step_pips * pip_size(symbol)
    if step <= 0:
        return False
    if side == Side.BUY:
        return current <= last_entry - step
    return current >= last_entry + step


@dataclass
class ScaleInPlan:
    allowed: bool
    leg: int = 0
    setup_id: str = ""
    lots: float = 0.0
    reason: str = ""


def plan_scale_in_entry(
    *,
    symbol: str,
    side: Side,
    balance: float,
    open_positions: list[Position],
    tick: Tick | None,
    settings: Settings,
    require_depth: bool,
    step_pips: float | None = None,
    at: datetime | None = None,
) -> ScaleInPlan:
    max_legs = int(getattr(settings, "scale_in_max_legs", 3))
    step = (
        float(step_pips)
        if step_pips is not None
        else scale_in_step_pips_for_session(settings, at)
    )
    legs = open_legs(open_positions, symbol=symbol, side=side)

    other_side = [
        p
        for p in open_positions
        if p.status == PositionStatus.OPEN
        and p.symbol == symbol
        and p.side != side
    ]
    if other_side:
        return ScaleInPlan(False, reason="Opposite-side position open — no scale-in")

    if len(legs) >= max_legs:
        return ScaleInPlan(False, reason=f"Scale-in max legs ({max_legs}) reached")

    leg = len(legs) + 1
    setup_id = setup_id_for_legs(legs) or ""

    if leg > 1:
        if tick is None:
            return ScaleInPlan(False, reason="No tick for scale-in depth check")
        last_entry = legs[-1].entry_price
        current = tick.bid if side == Side.BUY else tick.ask
        if require_depth and not price_depth_ok(
            side=side,
            last_entry=last_entry,
            current=current,
            step_pips=step,
            symbol=symbol,
        ):
            return ScaleInPlan(
                False,
                reason=f"Need {step:g}p deeper pullback for leg {leg}",
            )

    lots = scale_in_lots(balance, leg, settings)
    if setup_id == "":
        from app.models.domain import new_id

        setup_id = new_id()[:12]

    return ScaleInPlan(
        True,
        leg=leg,
        setup_id=setup_id,
        lots=lots,
        reason=f"Scale-in leg {leg}/{max_legs}",
    )


def evaluate_scale_in(
    request: OrderRequest,
    *,
    balance: float,
    open_positions: list[Position],
    tick: Tick | None,
    settings: Settings,
) -> RiskDecision:
    """Risk gate for scale-in paper accounts — allows up to N same-side legs."""
    if request.lots <= 0:
        return RiskDecision(False, "Lot size must be positive")

    if settings.max_daily_loss_pct > 0:
        # Re-use standard daily loss from first RiskManager instance pattern — skip here;
        # caller still runs after this only for scale-in accounts on paper.
        pass

    legs = open_legs(open_positions, symbol=request.symbol, side=request.side)
    max_legs = int(getattr(settings, "scale_in_max_legs", 3))

    if len(legs) >= max_legs and request.leg_index is None:
        return RiskDecision(False, f"Scale-in max legs ({max_legs}) reached")

    same_symbol_other = [
        p
        for p in open_positions
        if p.status == PositionStatus.OPEN
        and p.symbol == request.symbol
        and p.side != request.side
    ]
    if same_symbol_other:
        return RiskDecision(False, "Opposite-side position open")

    total_open = len([p for p in open_positions if p.status == PositionStatus.OPEN])
    if total_open >= max_legs and not legs:
        return RiskDecision(False, f"Max open positions ({max_legs}) reached")

    return RiskDecision(True, adjusted_lots=request.lots)


# Per-account throttle: account_id -> monotonic last add time
_last_leg_add_at: dict[str, float] = {}


def leg_add_cooldown_ok(account_id: str, cooldown_seconds: float) -> bool:
    last = _last_leg_add_at.get(account_id, 0.0)
    return (time.time() - last) >= cooldown_seconds


def mark_leg_added(account_id: str) -> None:
    _last_leg_add_at[account_id] = time.time()
