#!/usr/bin/env python3
"""Restore trade opened_at / closed_at from a backup paper_accounts.json (by ticket)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _index_trades(accounts: list[dict]) -> dict[str, dict[str, str | None]]:
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


def repair(*, target: Path, backup: Path, dry_run: bool = False) -> dict:
    current = json.loads(target.read_text(encoding="utf-8"))
    source = json.loads(backup.read_text(encoding="utf-8"))
    ref = _index_trades(source)
    restored = 0
    missing = 0
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
            if changed:
                restored += 1
    if not dry_run:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp.replace(target)
    return {"restored_trades": restored, "missing_tickets": missing, "accounts": len(current)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="paper_accounts.json to repair")
    parser.add_argument("backup", type=Path, help="backup paper_accounts.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = repair(target=args.target, backup=args.backup, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
