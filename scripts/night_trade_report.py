#!/usr/bin/env python3
"""Print PH night vs day trade stats from ML history + optional paper JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.analytics.night_monitor import build_night_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Night trade monitor report (PH 9PM–7AM)")
    parser.add_argument(
        "--ml-history",
        type=Path,
        default=ROOT / "data" / "ai_trade_history.jsonl",
        help="ML labeled history JSONL",
    )
    parser.add_argument(
        "--paper-accounts",
        type=Path,
        default=None,
        help="optional paper_accounts.json for live deduped trades",
    )
    args = parser.parse_args()

    paper_trades: list[dict] = []
    if args.paper_accounts and args.paper_accounts.exists():
        accounts = json.loads(args.paper_accounts.read_text(encoding="utf-8"))
        for acc in accounts:
            paper_trades.extend(acc.get("trades") or [])

    ml_path = args.ml_history if args.ml_history.exists() else None
    report = build_night_report(
        ml_history_path=ml_path,
        paper_trades=paper_trades or None,
    )
    print(json.dumps(report.as_dict(), indent=2))


if __name__ == "__main__":
    main()
