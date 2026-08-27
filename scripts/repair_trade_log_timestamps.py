#!/usr/bin/env python3
"""CLI wrapper — restore trade dates from ML history + backup JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.trade_log_repair import repair_trade_timestamps  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore trade opened_at / closed_at from ML history and/or backup JSON."
    )
    parser.add_argument("target", type=Path, help="paper_accounts.json to repair")
    parser.add_argument(
        "backup",
        type=Path,
        nargs="?",
        default=None,
        help="optional backup paper_accounts.json",
    )
    parser.add_argument(
        "--ml-history",
        type=Path,
        default=None,
        help="ai_trade_history.jsonl (best source for original dates)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = repair_trade_timestamps(
        target=args.target,
        backup=args.backup,
        ml_history=args.ml_history,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
