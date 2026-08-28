#!/usr/bin/env python3
"""JM FX PC Bridge Agent — fast JM FX → MT5 command delivery + MT5 → JM FX sync."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
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

# Fast command poll (JM FX → MT5) vs full file upload (MT5 → JM FX)
CMD_INTERVAL = 0.12
FULL_INTERVAL = 0.8


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


def fetch_command(base_url: str, token: str) -> dict:
    url = f"{base_url.rstrip('/')}/mt/remote/command?token={urllib.request.quote(token)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        return json.loads(resp.read().decode("utf-8"))


def apply_command(bridge_dir: Path, command: str) -> tuple[bool, str | None]:
    cmd_path = bridge_dir / COMMAND_FILE
    command = command.strip()
    if not command:
        return False, None
    current = (read_text(cmd_path) or "").strip()
    if command == current:
        return False, None
    write_text(cmd_path, command if command.endswith("\n") else command + "\n")
    return True, _command_id(command)


def burst_upload_ack(base_url: str, token: str, bridge_dir: Path, cmd_id: str) -> None:
    """Background: push MT5 ack to cloud quickly after command delivery."""
    ack_path = bridge_dir / FILES["ack"]
    deadline = time.time() + 35.0
    while time.time() < deadline:
        try:
            sync_once(base_url, token, bridge_dir)
        except Exception:
            pass
        ack = read_text(ack_path) or ""
        first = ack.strip().splitlines()[0] if ack.strip() else ""
        if first.startswith(cmd_id + ","):
            return
        time.sleep(0.15)


def main() -> int:
    parser = argparse.ArgumentParser(description="JM FX MT5 PC bridge sync agent")
    parser.add_argument(
        "--bridge-dir",
        type=Path,
        default=Path(os.environ.get("JM_MT5_BRIDGE_DIR", str(DEFAULT_BRIDGE))),
    )
    parser.add_argument("--url", default=os.environ.get("JM_FX_API", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("JM_MT_BRIDGE_TOKEN", DEFAULT_TOKEN))
    parser.add_argument(
        "--cmd-interval",
        type=float,
        default=float(os.environ.get("JM_CMD_INTERVAL", CMD_INTERVAL)),
        help="Command poll seconds (JM FX → MT5)",
    )
    parser.add_argument(
        "--full-interval",
        type=float,
        default=float(os.environ.get("JM_FULL_INTERVAL", FULL_INTERVAL)),
        help="Full sync seconds (MT5 → JM FX)",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    bridge_dir = args.bridge_dir.expanduser()
    if not bridge_dir.is_dir():
        print(f"ERROR: bridge folder not found: {bridge_dir}", file=sys.stderr)
        return 1

    print(f"JM FX PC Agent — fast bridge")
    print(f"  command poll: {args.cmd_interval}s  |  full sync: {args.full_interval}s")
    print(f"  folder: {bridge_dir}")
    print("Keep open while MT5 + JM_Forex_Bridge run.\n")

    last_full = 0.0
    last_status = "starting"
    pending_ack_threads: list[threading.Thread] = []

    while True:
        try:
            # FAST: JM FX → MT5 command only (~120ms)
            cmd_data = fetch_command(args.url, args.token)
            command = (cmd_data.get("command") or "").strip()
            written, cmd_id = apply_command(bridge_dir, command)
            if written and cmd_id:
                t = threading.Thread(
                    target=burst_upload_ack,
                    args=(args.url, args.token, bridge_dir, cmd_id),
                    daemon=True,
                )
                t.start()
                pending_ack_threads = [x for x in pending_ack_threads if x.is_alive()]
                pending_ack_threads.append(t)
                last_status = f"cmd→MT5 {cmd_id[:8]}"

            # SLOW: MT5 → JM FX full upload (status/ticks/ack)
            now = time.time()
            if now - last_full >= args.full_interval:
                result = sync_once(args.url, args.token, bridge_dir)
                last_full = now
                if result.get("written"):
                    last_status = "sync OK"
                # Also pick up command from full sync fallback
                full_cmd = (result.get("command") or "").strip()
                w2, cid2 = apply_command(bridge_dir, full_cmd)
                if w2 and cid2:
                    threading.Thread(
                        target=burst_upload_ack,
                        args=(args.url, args.token, bridge_dir, cid2),
                        daemon=True,
                    ).start()
                    last_status = f"cmd→MT5 {cid2[:8]}"

            print(f"\r  {last_status} · {time.strftime('%H:%M:%S')}", end="", flush=True)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:80]
            print(f"\r  HTTP {exc.code}: {detail}", end="", flush=True)
        except Exception as exc:
            print(f"\r  error: {exc}", end="", flush=True)

        if args.once:
            print()
            return 0
        time.sleep(max(0.05, args.cmd_interval))


if __name__ == "__main__":
    raise SystemExit(main())
