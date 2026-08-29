#!/usr/bin/env python3
"""Create the dedicated 3-leg scale-in paper demo account (isolated from live/MT accounts)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.paper_accounts.registry import PaperAccountRegistry  # noqa: E402

DEFAULT_LABEL = "Scale-in demo (3 legs)"
DEFAULT_CODE = "SCALE3"
DEFAULT_DEPOSIT = 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create JM FX paper account with 3-leg scale-in (other accounts unchanged)."
    )
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Account label")
    parser.add_argument("--code", default=DEFAULT_CODE, help="Pin account code (e.g. SCALE3)")
    parser.add_argument("--deposit", type=float, default=DEFAULT_DEPOSIT, help="Starting deposit")
    parser.add_argument("--store", type=Path, default=None, help="paper_accounts.json path")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    args = parser.parse_args()

    store = args.store or (ROOT / "backend" / "app" / "data" / "paper_accounts.json")
    settings = Settings()
    reg = PaperAccountRegistry(settings, store_path=store)

    label = (args.label or DEFAULT_LABEL).strip()
    code_u = (args.code or DEFAULT_CODE).strip().upper()
    existing = None
    for acc in reg.all():
        if acc.is_desk:
            continue
        if code_u and (acc.code or "").upper() == code_u:
            existing = acc
            break
        if acc.scale_in_mode and acc.label == label:
            existing = acc
            break

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "label": label,
                    "code": code_u,
                    "deposit": args.deposit,
                    "scale_in_max_legs": settings.scale_in_max_legs,
                    "scale_in_step_pips": settings.scale_in_step_pips,
                    "existing_code": existing.code if existing else None,
                },
                indent=2,
            )
        )
        return

    if existing:
        acct = existing
        if not acct.scale_in_mode:
            acct.scale_in_mode = True
            reg.save()
        created = False
    else:
        acct = reg.create(
            deposit=args.deposit,
            label=label,
            follow_auto=True,
            is_desk=False,
            scale_in_mode=True,
        )
        if code_u:
            acct.code = code_u
        reg.save()
        created = True

    from app.risk.scale_in import scale_in_lots

    lots = [
        scale_in_lots(acct.broker.deposit, leg, settings)
        for leg in range(1, settings.scale_in_max_legs + 1)
    ]

    out = {
        "ok": True,
        "created": created,
        "scale_in_mode": True,
        "label": acct.label,
        "account_id": acct.id,
        "account_code": acct.code,
        "token": acct.token,
        "deposit": acct.broker.deposit,
        "follow_auto": acct.follow_auto,
        "scale_in": {
            "max_legs": settings.scale_in_max_legs,
            "step_pips": settings.scale_in_step_pips,
            "lots_per_leg": lots,
            "note": "0.01/0.02/0.03 per $1k balance per leg (× balance tier)",
        },
        "next_steps": [
            "Login dashboard with account code + token above",
            "Hard refresh — badge shows Scale-in 3L",
            "Existing MT4 live (A76321) and other demos are unchanged",
        ],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
