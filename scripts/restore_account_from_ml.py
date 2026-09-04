#!/usr/bin/env python3
"""Restore one paper account trade log from ai_trade_history.jsonl labeled rows."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def index_backup_trades(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for acc in data:
        for t in acc.get("trades") or []:
            ticket = str(t.get("ticket") or "")
            if ticket:
                out[ticket] = t
    return out


def trades_from_ml(
    ml_path: Path,
    account_id: str,
    *,
    backup: dict[str, dict],
) -> list[dict]:
    rows: dict[str, dict] = {}
    with ml_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("account_id") != account_id:
                continue
            if row.get("event") != "labeled":
                continue
            ticket = str(row.get("ticket") or "")
            if not ticket:
                continue
            ctx = row.get("context") or {}
            b = backup.get(ticket, {})
            side = (ctx.get("side") or b.get("side") or "BUY").upper()
            strategy = ctx.get("strategy_raw") or ctx.get("strategy") or b.get("strategy") or "AI_ML"
            if strategy and not str(strategy).startswith("AI_ML") and "/" not in str(strategy):
                strategy = f"AI_ML/{strategy}"
            trade = {
                "id": row.get("id") or b.get("id") or str(uuid.uuid4()),
                "ticket": ticket,
                "symbol": b.get("symbol") or "XAUUSD",
                "side": side,
                "lots": float(b.get("lots") or 0.01),
                "entry": row.get("entry"),
                "stop_loss": row.get("stop_loss") if row.get("stop_loss") is not None else b.get("stop_loss"),
                "take_profit": row.get("take_profit") if row.get("take_profit") is not None else b.get("take_profit"),
                "exit": row.get("exit"),
                "status": "CLOSED",
                "strategy": strategy,
                "comment": b.get("comment") or "",
                "close_reason": row.get("close_reason") or b.get("close_reason"),
                "unrealized_pnl": 0.0,
                "realized_pnl": float(row.get("realized_pnl") or b.get("realized_pnl") or 0),
                "mode": row.get("mode") or b.get("mode") or "paper",
                "opened_at": row.get("opened_at"),
                "closed_at": row.get("closed_at"),
                "reject_reason": None,
            }
            rows[ticket] = trade
    ordered = sorted(rows.values(), key=lambda t: t.get("opened_at") or "")
    return ordered


def restore_account(
    *,
    store: Path,
    ml_history: Path,
    account_code: str,
    backup: Path | None = None,
    dry_run: bool = False,
) -> dict:
    data = json.loads(store.read_text(encoding="utf-8"))
    code_u = account_code.strip().upper()
    target = next((a for a in data if (a.get("code") or "").upper() == code_u), None)
    if target is None:
        raise SystemExit(f"Account not found: {account_code}")
    account_id = target["id"]
    backup_idx = index_backup_trades(backup) if backup else {}
    trades = trades_from_ml(ml_history, account_id, backup=backup_idx)
    if not trades:
        raise SystemExit(f"No labeled ML trades for {account_code} ({account_id})")
    deposit = float(target.get("deposit") or 1000.0)
    total_pnl = round(sum(float(t.get("realized_pnl") or 0) for t in trades), 2)
    balance = round(deposit + total_pnl, 2)
    before = len(target.get("trades") or [])
    target["trades"] = trades
    target["balance"] = balance
    result = {
        "account_code": account_code,
        "account_id": account_id,
        "trades_before": before,
        "trades_after": len(trades),
        "deposit": deposit,
        "total_realized_pnl": total_pnl,
        "balance": balance,
        "first_opened_at": trades[0].get("opened_at"),
        "last_closed_at": trades[-1].get("closed_at"),
        "dry_run": dry_run,
    }
    if not dry_run:
        tmp = store.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(store)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore account trades from ML history")
    parser.add_argument("code", help="Account code e.g. 03BDC3")
    parser.add_argument(
        "--store",
        type=Path,
        default=ROOT / "backend" / "app" / "data" / "paper_accounts.json",
    )
    parser.add_argument(
        "--ml-history",
        type=Path,
        default=ROOT / "data" / "ai_trade_history.jsonl",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=None,
        help="Optional paper_accounts backup for lots/strategy merge",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = restore_account(
        store=args.store,
        ml_history=args.ml_history,
        account_code=args.code,
        backup=args.backup,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
