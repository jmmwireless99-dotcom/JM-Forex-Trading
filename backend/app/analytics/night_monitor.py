"""Night-session trade monitoring — PH 9PM–6:59AM vs day desk."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.ai.features import session_bucket
from app.strategies.session import ASIA_PH_END, ASIA_PH_START, ph_hour


# PH 21:00–06:59 — overlap (SMC) + NY (VWAP) + early Asia (EMA_RSI)
NIGHT_PH_START = 21  # inclusive
NIGHT_PH_END = ASIA_PH_START  # exclusive (7 AM)

NIGHT_SESSIONS = frozenset({"overlap", "ny", "other"})  # off_hours → other bucket
DAY_SESSIONS = frozenset({"asia", "london"})


def is_ph_night(ts: datetime) -> bool:
    """True when Philippines local hour is 9PM–6:59AM."""
    h = ph_hour(ts.astimezone(timezone.utc))
    return h >= NIGHT_PH_START or h < NIGHT_PH_END


def ph_night_window_start(now: datetime) -> datetime:
    """Start of the current PH night block (most recent 9PM PH)."""
    utc = now.astimezone(timezone.utc)
    h = ph_hour(utc)
    # PH 9PM = UTC 13:00 same calendar UTC day (when h>=21 PH means utc hour 13+)
    # Simpler: walk back to when ph_hour crossed 21
    probe = utc
    if h >= NIGHT_PH_START:
        # same PH day night started at PH 21 = UTC (21-8)%24 = 13
        start_utc_hour = (NIGHT_PH_START - 8) % 24
        start = utc.replace(hour=start_utc_hour, minute=0, second=0, microsecond=0)
        if utc.hour < start_utc_hour:
            start -= timedelta(days=1)
        return start
    # before 7AM PH — night started yesterday PH 9PM
    start_utc_hour = (NIGHT_PH_START - 8) % 24
    start = (utc - timedelta(days=1)).replace(
        hour=start_utc_hour, minute=0, second=0, microsecond=0
    )
    return start


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dedupe_key(row: dict[str, Any]) -> str:
    opened = _parse_dt(row.get("opened_at"))
    ts = opened.isoformat() if opened else str(row.get("opened_at") or "")
    entry = row.get("entry")
    entry_s = f"{float(entry):.2f}" if entry is not None else ""
    return "|".join(
        [
            ts[:16],
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
            str(row.get("strategy") or ""),
            entry_s,
        ]
    )


def _bucket_row(row: dict[str, Any]) -> str:
    ctx = row.get("context") or {}
    if ctx.get("session"):
        return str(ctx["session"])
    opened = _parse_dt(row.get("opened_at"))
    if opened:
        return session_bucket(opened)
    return "other"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "net_pnl": 0.0}
    wins = sum(1 for r in rows if float(r.get("realized_pnl") or 0) > 0)
    losses = sum(1 for r in rows if float(r.get("realized_pnl") or 0) < 0)
    flat = len(rows) - wins - losses
    net = round(sum(float(r.get("realized_pnl") or 0) for r in rows), 2)
    n = len(rows)
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "flat": flat,
        "win_rate_pct": round(100.0 * wins / n, 1) if n else None,
        "net_pnl": net,
    }


def _load_ml_labeled(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "labeled" or row.get("label") is None:
                continue
            pnl = row.get("realized_pnl")
            if pnl is None:
                pnl = 1.0 if row.get("label") == 1 else -1.0
            out.append(
                {
                    "opened_at": row.get("opened_at"),
                    "closed_at": row.get("closed_at"),
                    "realized_pnl": float(pnl),
                    "strategy": (row.get("context") or {}).get("strategy_raw")
                    or row.get("context", {}).get("strategy"),
                    "side": (row.get("context") or {}).get("side"),
                    "session": _bucket_row(row),
                    "close_reason": row.get("close_reason"),
                    "win": row.get("label") == 1,
                }
            )
    return out


def _trades_from_accounts(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize paper trade rows; dedupe mirrored auto-fill books."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in trades:
        if (raw.get("status") or "").upper() != "CLOSED":
            continue
        key = _dedupe_key(raw)
        if key in seen:
            continue
        seen.add(key)
        opened = _parse_dt(raw.get("opened_at"))
        sess = session_bucket(opened) if opened else "other"
        out.append(
            {
                "opened_at": raw.get("opened_at"),
                "closed_at": raw.get("closed_at"),
                "realized_pnl": float(raw.get("realized_pnl") or 0),
                "strategy": raw.get("strategy"),
                "side": raw.get("side"),
                "session": sess,
                "close_reason": raw.get("close_reason"),
                "win": float(raw.get("realized_pnl") or 0) > 0,
            }
        )
    return out


@dataclass
class NightMonitorReport:
    as_of: str
    ph_night_window: str
    night_window_start_utc: str
    is_currently_night: bool
    alert: str | None
    alert_level: str  # ok | caution | warning
    ml_history: dict[str, Any] = field(default_factory=dict)
    paper_trades: dict[str, Any] = field(default_factory=dict)
    tonight: dict[str, Any] = field(default_factory=dict)
    last_7d: dict[str, Any] = field(default_factory=dict)
    by_night_session: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "ph_night_window": self.ph_night_window,
            "night_window_start_utc": self.night_window_start_utc,
            "is_currently_night": self.is_currently_night,
            "alert": self.alert,
            "alert_level": self.alert_level,
            "ml_history": self.ml_history,
            "paper_trades": self.paper_trades,
            "tonight": self.tonight,
            "last_7d": self.last_7d,
            "by_night_session": self.by_night_session,
            "recommendations": self.recommendations,
        }


def build_night_report(
    *,
    now: datetime | None = None,
    ml_history_path: str | Path | None = None,
    paper_trades: list[dict[str, Any]] | None = None,
    min_n_alert: int = 5,
    loss_wr_threshold: float = 45.0,
) -> NightMonitorReport:
    """Build night vs day stats from ML history + deduped paper trades."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    night_start = ph_night_window_start(now)
    ml_rows = _load_ml_labeled(Path(ml_history_path)) if ml_history_path else []
    paper_rows = _trades_from_accounts(paper_trades or [])

    def split_night_day(rows: list[dict[str, Any]]) -> tuple[list, list]:
        night, day = [], []
        for r in rows:
            opened = _parse_dt(r.get("opened_at"))
            if opened is None:
                continue
            (night if is_ph_night(opened) else day).append(r)
        return night, day

    ml_night, ml_day = split_night_day(ml_rows)
    pt_night, pt_day = split_night_day(paper_rows)

    tonight_ml = [r for r in ml_night if _parse_dt(r.get("opened_at")) and _parse_dt(r["opened_at"]) >= night_start]
    tonight_pt = [r for r in pt_night if _parse_dt(r.get("opened_at")) and _parse_dt(r["opened_at"]) >= night_start]

    seven_days = now - timedelta(days=7)
    last7_ml = [r for r in ml_night if _parse_dt(r.get("opened_at")) and _parse_dt(r["opened_at"]) >= seven_days]

    by_sess: dict[str, list] = {}
    for r in ml_night:
        by_sess.setdefault(r.get("session") or "other", []).append(r)

    ml_night_summary = _summarize(ml_night)
    ml_day_summary = _summarize(ml_day)
    tonight_summary = _summarize(tonight_ml or tonight_pt)
    last7_summary = _summarize(last7_ml)

    by_night_session = {
        k: _summarize(v) for k, v in sorted(by_sess.items(), key=lambda x: -len(x[1]))
    }

    alert = None
    alert_level = "ok"
    recommendations: list[str] = []

    ny = by_night_session.get("ny") or {}
    overlap = by_night_session.get("overlap") or {}

    if ny.get("n", 0) >= min_n_alert and (ny.get("win_rate_pct") or 100) < loss_wr_threshold:
        alert_level = "warning"
        alert = (
            f"NY session (PH 2–4AM, VWAP) win rate {ny['win_rate_pct']}% "
            f"on {ny['n']} trades — below {loss_wr_threshold}% target"
        )
        recommendations.append(
            "NY / EMA_VWAP: consider raising ML min_win_prob at night or stand aside until WR improves"
        )

    if overlap.get("n", 0) >= min_n_alert and (overlap.get("win_rate_pct") or 100) < loss_wr_threshold:
        level = "warning" if alert_level != "warning" else alert_level
        if alert_level == "ok":
            alert_level = "caution"
        msg = (
            f"Overlap session (PH 9PM–2AM, SMC) win rate {overlap['win_rate_pct']}% "
            f"on {overlap['n']} trades"
        )
        alert = f"{alert}; {msg}" if alert else msg
        recommendations.append(
            "Overlap / SMC: daily cap already 4 — watch for wide TP misses; ML gate is active"
        )

    if tonight_summary["n"] >= 3 and tonight_summary["net_pnl"] < 0:
        if alert_level == "ok":
            alert_level = "caution"
        tonight_alert = (
            f"Tonight PH (since 9PM): {tonight_summary['n']} trades, "
            f"net ${tonight_summary['net_pnl']}, "
            f"WR {tonight_summary['win_rate_pct']}%"
        )
        alert = f"{alert}; {tonight_alert}" if alert else tonight_alert

    if ml_night_summary["n"] and ml_day_summary["n"]:
        night_wr = ml_night_summary.get("win_rate_pct") or 0
        day_wr = ml_day_summary.get("win_rate_pct") or 0
        if night_wr + 5 < day_wr:
            recommendations.append(
                f"Historical: night WR {night_wr}% vs day {day_wr}% — prioritize EMA_RSI Asia (PH 7AM–9PM)"
            )

    if not recommendations:
        recommendations.append(
            "Monitor overlap (SMC) and NY (VWAP) — Asia day session historically strongest"
        )

    return NightMonitorReport(
        as_of=now.isoformat(),
        ph_night_window="PH 21:00–06:59 (Overlap · NY · Early Asia)",
        night_window_start_utc=night_start.isoformat(),
        is_currently_night=is_ph_night(now),
        alert=alert,
        alert_level=alert_level,
        ml_history={
            "path": str(ml_history_path) if ml_history_path else None,
            "night": ml_night_summary,
            "day": ml_day_summary,
            "night_sessions": by_night_session,
        },
        paper_trades={
            "night": _summarize(pt_night),
            "day": _summarize(pt_day),
            "source": "deduped_client_trades",
        },
        tonight={
            **_summarize(tonight_ml or tonight_pt),
            "trades": (tonight_ml or tonight_pt)[-12:],
            "source": "ml_history" if tonight_ml else "paper_trades",
        },
        last_7d=last7_summary,
        by_night_session=by_night_session,
        recommendations=recommendations,
    )
