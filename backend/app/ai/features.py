"""Feature extraction for trade outcome prediction."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from app.models.domain import Signal, TradeLog
from app.strategies.session import classify_session

_RSI_RE = re.compile(r"RSI\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_SOFT_RE = re.compile(r"\bsoft\b", re.IGNORECASE)


FEATURE_KEYS = (
    "bias",
    "side_buy",
    "soft_confirm",
    "strat_ema_rsi",
    "strat_smc",
    "strat_judas",
    "strat_trend",
    "strat_vwap",
    "sess_asia",
    "sess_london",
    "sess_overlap",
    "sess_ny",
    "sess_other",
    "hour_sin",
    "hour_cos",
    "risk_norm",
    "reward_r",
    "rsi_norm",
)


def _as_utc(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def session_bucket(ts: datetime | None) -> str:
    window = classify_session(_as_utc(ts))
    slot = (window.label or "").lower()
    if "asia" in slot:
        return "asia"
    if slot in {"london_ny_overlap", "overlap"} or "overlap" in slot:
        return "overlap"
    if "london" in slot:
        return "london"
    if "new_york" in slot or slot in {"ny", "newyork"}:
        return "ny"
    return "other"


def parse_soft_confirm(reason: str | None) -> bool:
    return bool(reason and _SOFT_RE.search(reason))


def parse_rsi(reason: str | None) -> float | None:
    if not reason:
        return None
    m = _RSI_RE.search(reason)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def strategy_bucket(name: str | None) -> str:
    n = (name or "").lower()
    if "ema_rsi" in n or n == "ema_rsi_scalp":
        return "ema_rsi"
    if "liquidity" in n or "smc" in n:
        return "smc"
    if "judas" in n or "london" in n:
        return "judas"
    if "trend" in n or "breakout" in n:
        return "trend"
    if "vwap" in n:
        return "vwap"
    return "other"


def _risk_reward(
    *,
    side: str,
    entry: float | None,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[float, float]:
    if entry is None or stop_loss is None:
        return 12.0, 1.8
    risk = abs(float(entry) - float(stop_loss))
    if risk <= 1e-9:
        risk = 12.0
    if take_profit is None:
        return risk, 1.8
    reward = abs(float(take_profit) - float(entry))
    return risk, max(reward / risk, 0.1)


def vectorize(
    *,
    strategy: str | None,
    side: str,
    reason: str | None,
    ts: datetime | None,
    entry: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    session: str | None = None,
) -> dict[str, float]:
    """Return a dense feature dict used by the logistic model."""
    side_u = (side or "").upper()
    sess = session or session_bucket(ts)
    strat = strategy_bucket(strategy)
    soft = 1.0 if parse_soft_confirm(reason) else 0.0
    rsi = parse_rsi(reason)
    risk, reward_r = _risk_reward(
        side=side_u, entry=entry, stop_loss=stop_loss, take_profit=take_profit
    )
    hour = _as_utc(ts).hour + _as_utc(ts).minute / 60.0
    feats = {k: 0.0 for k in FEATURE_KEYS}
    feats["bias"] = 1.0
    feats["side_buy"] = 1.0 if side_u == "BUY" else 0.0
    feats["soft_confirm"] = soft
    strat_key = f"strat_{strat}"
    if strat_key in feats:
        feats[strat_key] = 1.0
    sess_key = f"sess_{sess}" if f"sess_{sess}" in feats else "sess_other"
    feats[sess_key] = 1.0
    feats["hour_sin"] = math.sin(2 * math.pi * hour / 24.0)
    feats["hour_cos"] = math.cos(2 * math.pi * hour / 24.0)
    feats["risk_norm"] = min(max(risk / 25.0, 0.05), 4.0)
    feats["reward_r"] = min(max(reward_r / 3.0, 0.1), 2.5)
    feats["rsi_norm"] = ((rsi if rsi is not None else 50.0) - 50.0) / 50.0
    return feats


def features_from_signal(
    signal: Signal,
    *,
    entry: float | None = None,
    session: str | None = None,
) -> dict[str, float]:
    side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)
    price = entry
    if price is None:
        price = signal.limit_price
    return vectorize(
        strategy=signal.strategy,
        side=side,
        reason=signal.reason,
        ts=signal.timestamp,
        entry=price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        session=session,
    )


def features_from_trade(trade: TradeLog, *, session: str | None = None) -> dict[str, float]:
    side = trade.side.value if hasattr(trade.side, "value") else str(trade.side)
    return vectorize(
        strategy=trade.strategy,
        side=side,
        reason=trade.comment or trade.close_reason,
        ts=trade.opened_at,
        entry=trade.entry,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        session=session,
    )


def context_tags(
    *,
    strategy: str | None,
    side: str,
    reason: str | None,
    ts: datetime | None,
    session: str | None = None,
) -> dict[str, Any]:
    return {
        "strategy": strategy_bucket(strategy),
        "strategy_raw": strategy,
        "side": (side or "").upper(),
        "session": session or session_bucket(ts),
        "soft_confirm": parse_soft_confirm(reason),
        "rsi": parse_rsi(reason),
        "hour_utc": _as_utc(ts).hour,
    }
