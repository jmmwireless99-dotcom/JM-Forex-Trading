#!/usr/bin/env python3
"""Create or verify the dedicated JM FX account for XM MT4 real (live) trading."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.engine.trading_engine import TradingEngine  # noqa: F401, E402
from app.paper_accounts.registry import PaperAccountRegistry  # noqa: E402

DEFAULT_LABEL = "XM MT4 Real"
DEFAULT_DEPOSIT = 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify JM FX account for XM MT4 real/live (separate from demo + MT5)."
    )
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Account label")
    parser.add_argument("--code", default="", help="Pin account code (6 chars)")
    parser.add_argument("--deposit", type=float, default=DEFAULT_DEPOSIT, help="Initial display deposit")
    parser.add_argument(
        "--follow-auto",
        action="store_true",
        help="Enable auto-follow desk signals (default OFF for real accounts)",
    )
    parser.add_argument("--store", type=Path, default=None, help="paper_accounts.json path")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    args = parser.parse_args()

    store = args.store or (ROOT / "backend" / "app" / "data" / "paper_accounts.json")
    settings = Settings()
    reg = PaperAccountRegistry(settings, store_path=store)

    label = (args.label or DEFAULT_LABEL).strip()
    code_u = (args.code or "").strip().upper()
    existing = None
    for acc in reg.all():
        if acc.is_desk:
            continue
        if code_u and (acc.code or "").upper() == code_u:
            existing = acc
            break
        if acc.label == label:
            existing = acc
            break

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "label": label,
                    "code": code_u or None,
                    "deposit": args.deposit,
                    "follow_auto": args.follow_auto,
                    "existing_code": existing.code if existing else None,
                },
                indent=2,
            )
        )
        return

    if existing:
        acct = existing
        created = False
    else:
        acct = reg.create(
            deposit=args.deposit,
            label=label,
            follow_auto=args.follow_auto,
            is_desk=False,
        )
        if code_u:
            acct.code = code_u
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
        "mt4_real_login": settings.mt4_real_login or None,
        "env": {
            "JM_MT4_REAL_ACCOUNT_CODE": acct.code,
            "JM_MT4_REAL_LOGIN": settings.mt4_real_login or "",
            "JM_MT4_REAL_BRIDGE_DIR": settings.mt4_real_bridge_dir or "(set path to real MT4 Common\\Files)",
            "JM_MT4_SYMBOL": settings.mt4_symbol,
        },
        "next_steps": [
            "Set JM_MT4_REAL_ACCOUNT_CODE in server .env",
            "Set JM_MT4_REAL_BRIDGE_DIR to REAL MT4 Terminal Common\\Files (must differ from demo + MT5 dirs)",
            "Set JM_MT4_REAL_LOGIN to your XM MT4 live account number",
            "Login dashboard with account code + token",
            "Attach JM_Forex_Bridge.mq4 on XAUUSD chart on the REAL MT4 terminal only",
            "Real account does NOT auto-follow desk signals unless --follow-auto was used",
        ],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
