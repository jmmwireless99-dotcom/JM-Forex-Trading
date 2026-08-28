#!/usr/bin/env python3
"""Create a dedicated JM FX account for XM MT5 demo trading."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.engine.trading_engine import TradingEngine  # noqa: F401, E402 — breaks import cycle
from app.paper_accounts.registry import PaperAccountRegistry  # noqa: E402

DEFAULT_LABEL = "XM MT5 Demo"
DEFAULT_DEPOSIT = 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create dedicated JM FX account for XM MT5 demo journal/UI."
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Account label (default: {DEFAULT_LABEL})",
    )
    parser.add_argument(
        "--deposit",
        type=float,
        default=DEFAULT_DEPOSIT,
        help="Starting paper deposit for sizing preview (default: 1000)",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="paper_accounts.json path (default: backend/app/data/paper_accounts.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without saving",
    )
    args = parser.parse_args()

    store = args.store or (ROOT / "backend" / "app" / "data" / "paper_accounts.json")
    settings = Settings()
    reg = PaperAccountRegistry(settings, store_path=store)

    label = (args.label or DEFAULT_LABEL).strip()
    existing = None
    for acc in reg.all():
        if acc.label == label and not acc.is_desk:
            existing = acc
            break

    if existing and not args.dry_run:
        acct = existing
        created = False
    else:
        if args.dry_run:
            print(json.dumps({"dry_run": True, "label": label, "deposit": args.deposit}, indent=2))
            return
        acct = reg.create(
            deposit=args.deposit,
            label=label,
            follow_auto=False,
            is_desk=False,
        )
        reg.save()
        created = True

    out = {
        "ok": True,
        "created": created,
        "label": acct.label,
        "account_id": acct.id,
        "account_code": acct.code,
        "token": acct.token,
        "deposit": acct.broker.deposit,
        "follow_auto": acct.follow_auto,
        "env": {
            "JM_MT5_DEMO_ACCOUNT_CODE": acct.code,
            "JM_EXECUTION_MODE": "mt5",
        },
        "next_steps": [
            "Add JM_MT5_DEMO_ACCOUNT_CODE to .env on the JM FX server",
            "Restart jm-forex service",
            "Login to dashboard with this account (save token in browser)",
            "See docs/XM_MT5_SETUP.md for MT5 EA install",
        ],
        "security": "Keep token secret — do not commit to git or share publicly",
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
