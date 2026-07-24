"""In-memory store for Windows ↔ cloud MetaTrader remote bridges (MT4 + MT5)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RemoteMtState:
    status_csv: str = ""
    ticks_csv: str = ""
    positions_csv: str = ""
    history_csv: str = ""
    ack_csv: str = ""
    last_push_at: float = 0.0
    agent_host: str = ""
    symbol: str = "XAUUSD"
    mt_login: str = ""
    platform: str = "mt5"
    trade_ok: bool | None = None
    trade_block: str = ""
    pending_command_csv: str = ""
    pending_command_id: str = ""
    pending_set_at: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock)


_STATES: dict[str, RemoteMtState] = {
    "mt4": RemoteMtState(platform="mt4"),
    "mt5": RemoteMtState(platform="mt5"),
}


def normalize_platform(platform: str | None) -> str:
    p = (platform or "mt5").strip().lower()
    if p in {"mt4", "4", "mql4"}:
        return "mt4"
    return "mt5"


def get_remote_mt_state(platform: str | None = "mt5") -> RemoteMtState:
    return _STATES[normalize_platform(platform)]


def remote_push(
    *,
    status_csv: str = "",
    ticks_csv: str = "",
    positions_csv: str = "",
    history_csv: str = "",
    ack_csv: str = "",
    symbol: str = "",
    agent_host: str = "",
    platform: str | None = "mt5",
) -> dict:
    plat = normalize_platform(platform)
    st = _STATES[plat]
    with st.lock:
        if status_csv:
            st.status_csv = status_csv
            # ok,balance,equity,positions,time[,login[,trade_ok[,block]]]
            line = status_csv.strip().splitlines()[-1] if status_csv.strip() else ""
            parts = line.split(",")
            if len(parts) >= 6 and str(parts[5]).strip().isdigit():
                st.mt_login = str(parts[5]).strip()
            else:
                st.mt_login = ""
            if len(parts) >= 7 and str(parts[6]).strip() in {"0", "1"}:
                st.trade_ok = str(parts[6]).strip() == "1"
                st.trade_block = str(parts[7]).strip() if len(parts) >= 8 else ""
            else:
                st.trade_ok = None
                st.trade_block = ""
        if ticks_csv:
            st.ticks_csv = ticks_csv
        if positions_csv:
            st.positions_csv = positions_csv
        if history_csv:
            st.history_csv = history_csv
        if ack_csv:
            st.ack_csv = ack_csv
        if symbol:
            st.symbol = symbol.upper()
        if agent_host:
            st.agent_host = agent_host
        st.last_push_at = time.time()
        pending = None
        if st.pending_command_csv:
            pending = {
                "id": st.pending_command_id,
                "csv": st.pending_command_csv,
            }
        return {
            "ok": True,
            "online": True,
            "platform": plat,
            "last_push_at": st.last_push_at,
            "pending_command": bool(st.pending_command_csv),
            "command": pending,
            "mt_login": st.mt_login or None,
            "age_seconds": 0.0,
            "has_history": bool(st.history_csv.strip()),
        }


def remote_poll_command(platform: str | None = "mt5") -> dict:
    st = _STATES[normalize_platform(platform)]
    with st.lock:
        if not st.pending_command_csv:
            return {"command": None, "platform": st.platform}
        return {
            "platform": st.platform,
            "command": {
                "id": st.pending_command_id,
                "csv": st.pending_command_csv,
            },
        }


def remote_clear_command(
    command_id: str | None = None, platform: str | None = "mt5"
) -> None:
    st = _STATES[normalize_platform(platform)]
    with st.lock:
        if command_id and st.pending_command_id and command_id != st.pending_command_id:
            return
        st.pending_command_csv = ""
        st.pending_command_id = ""
        st.pending_set_at = 0.0


def remote_set_command(
    command_id: str, csv_payload: str, platform: str | None = "mt5"
) -> None:
    st = _STATES[normalize_platform(platform)]
    with st.lock:
        st.pending_command_id = command_id
        st.pending_command_csv = csv_payload
        st.pending_set_at = time.time()
        st.ack_csv = ""


def remote_is_online(
    max_age_seconds: float = 8.0, platform: str | None = "mt5"
) -> bool:
    st = _STATES[normalize_platform(platform)]
    with st.lock:
        if st.last_push_at <= 0:
            return False
        return (time.time() - st.last_push_at) <= max_age_seconds


def remote_any_online(max_age_seconds: float = 8.0) -> bool:
    return remote_is_online(max_age_seconds, "mt5") or remote_is_online(
        max_age_seconds, "mt4"
    )


def remote_snapshot_info(platform: str | None = None) -> dict:
    """Single-platform snapshot, or combined when platform is None."""
    if platform is not None:
        plat = normalize_platform(platform)
        st = _STATES[plat]
        with st.lock:
            age = (time.time() - st.last_push_at) if st.last_push_at else None
            return {
                "configured": True,
                "transport": "remote",
                "platform": plat,
                "online": remote_is_online(platform=plat),
                "last_push_at": st.last_push_at or None,
                "age_seconds": round(age, 2) if age is not None else None,
                "agent_host": st.agent_host or None,
                "symbol": st.symbol,
                "mt_login": st.mt_login or None,
                "trade_ok": st.trade_ok,
                "trade_block": st.trade_block or None,
                "pending_command": bool(st.pending_command_csv),
                "bridge_dir": f"remote://windows-agent/{plat}",
            }
    mt5 = remote_snapshot_info("mt5")
    mt4 = remote_snapshot_info("mt4")
    primary = mt5 if mt5.get("online") else mt4 if mt4.get("online") else mt5
    return {
        **primary,
        "platforms": {"mt5": mt5, "mt4": mt4},
        "online": bool(mt5.get("online") or mt4.get("online")),
        "bridge_dir": "remote://windows-agent",
    }


def remote_mt_login(platform: str | None = "mt5") -> str | None:
    st = _STATES[normalize_platform(platform)]
    with st.lock:
        return st.mt_login or None
