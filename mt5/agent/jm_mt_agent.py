"""
JM Forex — Windows MT5 remote agent

Runs on the SAME PC as MetaTrader 5.
Reads/writes Common\\Files CSV from JM_Forex_Bridge EA,
and syncs with the cloud desk at https://jmtechsolution.cloud/fx/

Setup:
  1. Attach JM_Forex_Bridge EA on XAUUSD (UseCommonFolder=true)
  2. Edit config.json — set bridge_token from Joel / server
  3. Double-click RUN_AGENT.bat  (or: py -3 jm_mt_agent.py)

Requires: Python 3.10+ (stdlib only — no pip packages).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API = "https://jmtechsolution.cloud/fx/api"
DEFAULT_FOLDER = Path(
    os.environ.get(
        "JM_MT_FILES",
        str(Path.home() / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"),
    )
)


def load_config() -> dict:
    here = Path(__file__).resolve().parent
    cfg_path = here / "config.json"
    data = {
        "api_base": DEFAULT_API,
        "bridge_token": "",
        "files_dir": str(DEFAULT_FOLDER),
        "symbol": "XAUUSD",
        "poll_ms": 500,
    }
    if cfg_path.exists():
        try:
            data.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] config.json: {exc}")
    # Env overrides
    if os.environ.get("JM_API_BASE"):
        data["api_base"] = os.environ["JM_API_BASE"].rstrip("/")
    if os.environ.get("JM_MT_BRIDGE_TOKEN"):
        data["bridge_token"] = os.environ["JM_MT_BRIDGE_TOKEN"]
    if os.environ.get("JM_MT_FILES"):
        data["files_dir"] = os.environ["JM_MT_FILES"]
    if os.environ.get("JM_MT_SYMBOL"):
        data["symbol"] = os.environ["JM_MT_SYMBOL"]
    data["api_base"] = str(data["api_base"]).rstrip("/")
    if not str(data.get("files_dir") or "").strip():
        data["files_dir"] = str(DEFAULT_FOLDER)
    return data


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def http_json(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None
    headers = {
        "Accept": "application/json",
        "X-JM-Bridge-Token": token,
        "User-Agent": "JM-MT-Agent/1.0",
    }
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        data = raw
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def main() -> int:
    cfg = load_config()
    token = (cfg.get("bridge_token") or "").strip()
    if not token or token.startswith("PASTE_"):
        print("ERROR: set bridge_token in config.json (ask Joel / server admin).")
        print("File:", Path(__file__).resolve().parent / "config.json")
        return 1

    files_dir = Path(cfg["files_dir"])
    api = cfg["api_base"]
    symbol = str(cfg.get("symbol") or "XAUUSD").upper()
    poll_s = max(0.25, float(cfg.get("poll_ms", 500)) / 1000.0)
    host = socket.gethostname()

    status_f = files_dir / "jm_status.csv"
    ticks_f = files_dir / "jm_ticks.csv"
    positions_f = files_dir / "jm_positions.csv"
    command_f = files_dir / "jm_command.csv"
    ack_f = files_dir / "jm_ack.csv"

    print("JM Forex MT5 remote agent")
    print("  API     :", api)
    print("  Files   :", files_dir)
    print("  Symbol  :", symbol)
    print("  Host    :", host)
    print("Keep MT5 open with JM_Forex_Bridge EA on the chart. Ctrl+C to stop.")
    print("-" * 60)

    if not files_dir.exists():
        print("WARNING: files folder missing — create/open:")
        print(" ", files_dir)
        print(" Win+R → %APPDATA%\\MetaQuotes\\Terminal\\Common\\Files")

    last_cmd_id = ""
    last_ack = ""
    ok_pushes = 0
    while True:
        try:
            status_csv = read_text(status_f)
            ticks_csv = read_text(ticks_f)
            positions_csv = read_text(positions_f)
            ack_csv = read_text(ack_f)

            clear_id = None
            if ack_csv and ack_csv.strip() != last_ack:
                last_ack = ack_csv.strip()
                # first field is command id
                clear_id = last_ack.split(",", 1)[0].strip() or None

            push = http_json(
                "POST",
                f"{api}/mt/remote/push",
                token,
                {
                    "status_csv": status_csv,
                    "ticks_csv": ticks_csv,
                    "positions_csv": positions_csv,
                    "ack_csv": ack_csv,
                    "symbol": symbol,
                    "agent_host": host,
                    "clear_command_id": clear_id,
                },
            )
            ok_pushes += 1
            if ok_pushes == 1 or ok_pushes % 20 == 0:
                online = push.get("ok")
                print(
                    f"[{time.strftime('%H:%M:%S')}] push ok={online} "
                    f"status={'yes' if status_csv else 'NO'} "
                    f"ticks={'yes' if ticks_csv else 'NO'}"
                )

            poll = http_json("GET", f"{api}/mt/remote/poll", token)
            cmd = (poll or {}).get("command")
            if cmd and cmd.get("csv"):
                cmd_id = str(cmd.get("id") or "")
                if cmd_id and cmd_id != last_cmd_id:
                    write_text(command_f, cmd["csv"])
                    last_cmd_id = cmd_id
                    print(f"[{time.strftime('%H:%M:%S')}] command → EA id={cmd_id}")

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            print(f"[error] HTTP {exc.code}: {body[:200]}")
            time.sleep(2)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}")
            time.sleep(2)

        time.sleep(poll_s)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAgent stopped.")
        raise SystemExit(0)
