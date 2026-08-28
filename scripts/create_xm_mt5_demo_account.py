#!/usr/bin/env python3
"""Create or verify the dedicated JM FX account for XM MT5 demo trading."""

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

DEFAULT_LABEL = "XM MT5 Demo"
DEFAULT_DEPOSIT = 1000.0
DEFAULT_CODE = "DDDC3D"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify JM FX account for XM MT5 demo (login 169250320)."
    )
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Account label")
    parser.add_argument("--code", default="", help="Pin account code (e.g. DDDC3D)")
    parser.add_argument("--deposit", type=float, default=DEFAULT_DEPOSIT, help="Paper deposit")
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
        acct = reg.create(deposit=args.deposit, label=label, follow_auto=True, is_desk=False)
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
        "mt5_login": settings.mt5_demo_login,
        "env": {
            "JM_MT5_DEMO_ACCOUNT_CODE": acct.code,
            "JM_MT5_DEMO_LOGIN": settings.mt5_demo_login,
            "JM_MT_SYMBOL": settings.mt_symbol,
        },
        "next_steps": [
            "Set JM_MT5_DEMO_ACCOUNT_CODE in server .env",
            "Run scripts/setup_mt5_remote_bridge.sh with JM_MT_SYMBOL=GOLD#",
            "Login dashboard with account code + token",
            "Attach JM_Forex_Bridge on GOLD# chart (InpSymbol=GOLD#)",
        ],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
