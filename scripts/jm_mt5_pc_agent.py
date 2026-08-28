#!/usr/bin/env python3
"""JM FX PC Bridge Agent — sync MT5 Common\\Files ↔ cloud (no Syncthing).

Run on the Windows PC where XM MT5 + JM_Forex_Bridge EA are active.

  python jm_mt5_pc_agent.py

Or double-click: scripts/start-jm-mt5-agent.bat
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://jmtechsolution.cloud/fx/api"
DEFAULT_TOKEN = "gTXmD7O-194jS9gveB1I5c9qjmNdqdUv"
DEFAULT_BRIDGE = Path.home() / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"

FILES = {
    "status": "jm_status.csv",
    "ticks": "jm_ticks.csv",
    "positions": "jm_positions.csv",
    "ack": "jm_ack.csv",
}
COMMAND_FILE = "jm_command.csv"


def read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _command_id(command: str) -> str | None:
    for line in command.strip().splitlines():
        if not line or line.startswith("id,action"):
            continue
        return line.split(",", 1)[0].strip() or None
    return None


def sync_once(base_url: str, token: str, bridge_dir: Path) -> dict:
    payload = {"token": token}
    for key, fname in FILES.items():
        text = read_text(bridge_dir / fname)
        if text is not None:
            payload[key] = text

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/mt/remote/sync",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    command = (data.get("command") or "").strip()
    cmd_path = bridge_dir / COMMAND_FILE
    if command:
        current = (read_text(cmd_path) or "").strip()
        if command != current:
            write_text(cmd_path, command if command.endswith("\n") else command + "\n")
            data["command_written"] = True
            data["command_id"] = _command_id(command)
    return data


def burst_sync_ack(
    base_url: str,
    token: str,
    bridge_dir: Path,
    cmd_id: str,
    *,
    seconds: float = 40.0,
) -> bool:
    """Fast sync loop after a new command — upload MT5 ack quickly."""
    ack_path = bridge_dir / FILES["ack"]
    deadline = time.time() + seconds
    while time.time() < deadline:
        sync_once(base_url, token, bridge_dir)
        ack = read_text(ack_path) or ""
        first = ack.strip().splitlines()[0] if ack.strip() else ""
        if first.startswith(cmd_id + ","):
            return True
        time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="JM FX MT5 PC bridge sync agent")
    parser.add_argument(
        "--bridge-dir",
        type=Path,
        default=Path(os.environ.get("JM_MT5_BRIDGE_DIR", str(DEFAULT_BRIDGE))),
        help="MT5 Common\\Files folder",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("JM_FX_API", DEFAULT_URL),
        help="JM FX API base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("JM_MT_BRIDGE_TOKEN", DEFAULT_TOKEN),
        help="Bridge token (must match server JM_MT_BRIDGE_TOKEN)",
    )
    parser.add_argument("--interval", type=float, default=0.5, help="Sync interval seconds")
    parser.add_argument("--once", action="store_true", help="Single sync then exit")
    args = parser.parse_args()

    bridge_dir = args.bridge_dir.expanduser()
    if not bridge_dir.is_dir():
        print(f"ERROR: bridge folder not found: {bridge_dir}", file=sys.stderr)
        print("Open MT5 → File → Open Data Folder → MQL5 → .. → Common → Files", file=sys.stderr)
        return 1

    print(f"JM FX PC Agent — syncing {bridge_dir}")
    print(f"  → {args.url}/mt/remote/sync")
    print("Keep this window open while MT5 + JM_Forex_Bridge are running.")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            result = sync_once(args.url, args.token, bridge_dir)
            status = "online" if result.get("written") else "waiting"
            extra = ""
            if result.get("command_written"):
                cmd_id = result.get("command_id") or "?"
                extra = f" cmd→MT5 {cmd_id[:8]}"
                if burst_sync_ack(args.url, args.token, bridge_dir, cmd_id):
                    extra += " ack✓"
                else:
                    extra += " ack…"
            print(f"\r  sync OK · {status}{extra} · {time.strftime('%H:%M:%S')}", end="", flush=True)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:120]
            print(f"\r  HTTP {exc.code}: {detail}", end="", flush=True)
        except Exception as exc:
            print(f"\r  error: {exc}", end="", flush=True)
        if args.once:
            print()
            return 0
        time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
