"""In-memory store for the Windows ↔ cloud MetaTrader remote bridge."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RemoteMtState:
    status_csv: str = ""
    ticks_csv: str = ""
    positions_csv: str = ""
    ack_csv: str = ""
    last_push_at: float = 0.0
    agent_host: str = ""
    symbol: str = "XAUUSD"
    pending_command_csv: str = ""
    pending_command_id: str = ""
    pending_set_at: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock)


_STATE = RemoteMtState()


def get_remote_mt_state() -> RemoteMtState:
    return _STATE


def remote_push(
    *,
    status_csv: str = "",
    ticks_csv: str = "",
    positions_csv: str = "",
    ack_csv: str = "",
    symbol: str = "",
    agent_host: str = "",
) -> dict:
    st = _STATE
    with st.lock:
        if status_csv:
            st.status_csv = status_csv
        if ticks_csv:
            st.ticks_csv = ticks_csv
        if positions_csv:
            st.positions_csv = positions_csv
        if ack_csv:
            st.ack_csv = ack_csv
        if symbol:
            st.symbol = symbol.upper()
        if agent_host:
            st.agent_host = agent_host
        st.last_push_at = time.time()
        age = 0.0
        return {
            "ok": True,
            "online": True,
            "last_push_at": st.last_push_at,
            "pending_command": bool(st.pending_command_csv),
            "age_seconds": age,
        }


def remote_poll_command() -> dict:
    st = _STATE
    with st.lock:
        if not st.pending_command_csv:
            return {"command": None}
        return {
            "command": {
                "id": st.pending_command_id,
                "csv": st.pending_command_csv,
            }
        }


def remote_clear_command(command_id: str | None = None) -> None:
    st = _STATE
    with st.lock:
        if command_id and st.pending_command_id and command_id != st.pending_command_id:
            return
        st.pending_command_csv = ""
        st.pending_command_id = ""
        st.pending_set_at = 0.0


def remote_set_command(command_id: str, csv_payload: str) -> None:
    st = _STATE
    with st.lock:
        st.pending_command_id = command_id
        st.pending_command_csv = csv_payload
        st.pending_set_at = time.time()
        st.ack_csv = ""


def remote_is_online(max_age_seconds: float = 8.0) -> bool:
    st = _STATE
    with st.lock:
        if st.last_push_at <= 0:
            return False
        return (time.time() - st.last_push_at) <= max_age_seconds


def remote_snapshot_info() -> dict:
    st = _STATE
    with st.lock:
        age = (time.time() - st.last_push_at) if st.last_push_at else None
        return {
            "configured": True,
            "transport": "remote",
            "online": remote_is_online(),
            "last_push_at": st.last_push_at or None,
            "age_seconds": round(age, 2) if age is not None else None,
            "agent_host": st.agent_host or None,
            "symbol": st.symbol,
            "pending_command": bool(st.pending_command_csv),
            "bridge_dir": "remote://windows-agent",
        }
