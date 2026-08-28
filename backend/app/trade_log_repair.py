"""Restore trade opened_at / closed_at from ML history and/or backup JSON."""

from __future__ import annotations

import json
from pathlib import Path


def index_json_accounts(accounts: list[dict]) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    for acc in accounts:
        for trade in acc.get("trades") or []:
            ticket = trade.get("ticket")
            if not ticket:
                continue
            out[str(ticket)] = {
                "opened_at": trade.get("opened_at"),
                "closed_at": trade.get("closed_at"),
            }
    return out


def index_ml_history(path: Path) -> dict[str, dict[str, str | None]]:
    """Best row per ticket from ai_trade_history.jsonl (labeled preferred)."""
    out: dict[str, dict[str, str | None]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ticket = row.get("ticket")
            if not ticket:
                continue
            ticket = str(ticket)
            prev = out.get(ticket)
            event = row.get("event")
            candidate = {
                "opened_at": row.get("opened_at"),
                "closed_at": row.get("closed_at"),
            }
            if prev is None:
                out[ticket] = candidate
                continue
            if event == "labeled":
                out[ticket] = candidate
            elif prev.get("closed_at") is None and candidate.get("closed_at"):
                out[ticket] = candidate
    return out


def merge_timestamp_sources(
    *sources: dict[str, dict[str, str | None]],
) -> dict[str, dict[str, str | None]]:
    merged: dict[str, dict[str, str | None]] = {}
    for src in sources:
        for ticket, row in src.items():
            cur = merged.get(ticket, {})
            merged[ticket] = {
                "opened_at": row.get("opened_at") or cur.get("opened_at"),
                "closed_at": row.get("closed_at") or cur.get("closed_at"),
            }
    return merged


def repair_trade_timestamps(
    *,
    target: Path,
    backup: Path | None = None,
    ml_history: Path | None = None,
    dry_run: bool = False,
) -> dict:
    current = json.loads(target.read_text(encoding="utf-8"))
    refs: list[dict[str, dict[str, str | None]]] = []
    if ml_history is not None:
        refs.append(index_ml_history(ml_history))
    if backup is not None and backup.exists():
        backup_data = json.loads(backup.read_text(encoding="utf-8"))
        refs.append(index_json_accounts(backup_data))
    ref = merge_timestamp_sources(*refs) if refs else {}

    restored = 0
    missing = 0
    opened_fixes = 0
    closed_fixes = 0
    for acc in current:
        for trade in acc.get("trades") or []:
            ticket = str(trade.get("ticket") or "")
            if not ticket or ticket not in ref:
                missing += 1
                continue
            ref_row = ref[ticket]
            changed = False
            for field in ("opened_at", "closed_at"):
                old = trade.get(field)
                new = ref_row.get(field)
                if new and old != new:
                    trade[field] = new
                    changed = True
                    if field == "opened_at":
                        opened_fixes += 1
                    else:
                        closed_fixes += 1
            if changed:
                restored += 1
    if not dry_run and restored:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp.replace(target)
    return {
        "restored_trades": restored,
        "opened_at_fixes": opened_fixes,
        "closed_at_fixes": closed_fixes,
        "missing_tickets": missing,
        "reference_tickets": len(ref),
        "accounts": len(current),
    }
