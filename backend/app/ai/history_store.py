"""Append-only JSONL store for ML trade history."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.domain import utcnow


class TradeHistoryStore:
    """Persistent feature history used to train the decision model."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: list[dict[str, Any]] | None = None

    def _read_all(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        rows: list[dict[str, Any]] = []
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        self._cache = rows
        return rows

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            if self._cache is not None:
                self._cache.append(row)
        return row

    def record_open(
        self,
        *,
        ticket: str,
        account_id: str | None,
        features: dict[str, float],
        context: dict[str, Any],
        entry: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        mode: str = "paper",
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid4()),
            "event": "open",
            "ticket": ticket,
            "account_id": account_id,
            "features": features,
            "context": context,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "mode": mode,
            "label": None,
            "realized_pnl": None,
            "close_reason": None,
            "opened_at": utcnow().isoformat(),
            "closed_at": None,
        }
        return self._append(row)

    def record_close(
        self,
        *,
        ticket: str,
        realized_pnl: float | None,
        close_reason: str | None,
        exit_price: float | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            rows = list(self._read_all())
            target = None
            for row in reversed(rows):
                if row.get("ticket") == ticket and row.get("event") in {"open", "labeled"}:
                    target = row
                    break
            if target is None:
                return None
            label = None
            if realized_pnl is not None:
                label = 1 if float(realized_pnl) > 0 else 0
            labeled = {
                **target,
                "event": "labeled",
                "label": label,
                "realized_pnl": realized_pnl,
                "close_reason": close_reason,
                "exit": exit_price,
                "closed_at": utcnow().isoformat(),
            }
            # Rewrite file with updated row (small histories — fine for desk scale)
            for i, row in enumerate(rows):
                if row.get("id") == target.get("id"):
                    rows[i] = labeled
                    break
            else:
                rows.append(labeled)
            tmp = self.path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
            tmp.replace(self.path)
            self._cache = rows
            return labeled

    def labeled(self) -> list[dict[str, Any]]:
        return [r for r in self._read_all() if r.get("event") == "labeled" and r.get("label") is not None]

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._read_all()
        return list(reversed(rows[-limit:]))

    def bucket_stats(
        self,
        *,
        strategy: str | None = None,
        side: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Win/loss counts for a strategy/side/session slice of labeled history."""
        wins = 0
        n = 0
        side_u = (side or "").upper() or None
        for row in self.labeled():
            ctx = row.get("context") or {}
            if strategy is not None and (ctx.get("strategy") or "") != strategy:
                continue
            if side_u is not None and (ctx.get("side") or "").upper() != side_u:
                continue
            if session is not None and (ctx.get("session") or "") != session:
                continue
            n += 1
            if row.get("label") == 1:
                wins += 1
        return {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": (wins / n) if n else None,
        }

    def stats(self) -> dict[str, Any]:
        labeled = self.labeled()
        wins = [r for r in labeled if r.get("label") == 1]
        losses = [r for r in labeled if r.get("label") == 0]
        by_session: dict[str, dict[str, int]] = {}
        by_soft = {"soft": {"n": 0, "wins": 0}, "hard": {"n": 0, "wins": 0}}
        for r in labeled:
            sess = (r.get("context") or {}).get("session") or "other"
            bucket = by_session.setdefault(sess, {"n": 0, "wins": 0})
            bucket["n"] += 1
            if r.get("label") == 1:
                bucket["wins"] += 1
            soft = bool((r.get("context") or {}).get("soft_confirm"))
            key = "soft" if soft else "hard"
            by_soft[key]["n"] += 1
            if r.get("label") == 1:
                by_soft[key]["wins"] += 1

        def rate(bucket: dict[str, int]) -> float | None:
            n = bucket.get("n") or 0
            if not n:
                return None
            return round(100.0 * bucket.get("wins", 0) / n, 1)

        return {
            "total_events": len(self._read_all()),
            "labeled": len(labeled),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(100.0 * len(wins) / len(labeled), 1) if labeled else None,
            "by_session": {
                k: {"n": v["n"], "wins": v["wins"], "win_rate_pct": rate(v)}
                for k, v in sorted(by_session.items())
            },
            "by_confirm": {
                k: {"n": v["n"], "wins": v["wins"], "win_rate_pct": rate(v)}
                for k, v in by_soft.items()
            },
            "path": str(self.path),
        }
