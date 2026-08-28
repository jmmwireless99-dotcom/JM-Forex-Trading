"""Server-side bridge folder updated by the Windows PC sync agent."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def remote_bridge_dir(settings: Settings) -> Path | None:
    """Directory where the PC agent writes jm_*.csv copies."""
    if not settings.mt_remote_bridge:
        return None
    path = (settings.mt5_bridge_dir or settings.mt4_bridge_dir or "").strip()
    if not path:
        return None
    return Path(path)


def ensure_remote_bridge_dir(settings: Settings) -> Path:
    root = remote_bridge_dir(settings)
    if root is None:
        raise ValueError("JM_MT_REMOTE_BRIDGE requires JM_MT5_BRIDGE_DIR")
    root.mkdir(parents=True, exist_ok=True)
    return root


def verify_bridge_token(settings: Settings, token: str | None) -> None:
    expected = (settings.mt_bridge_token or "").strip()
    if not expected:
        raise ValueError("JM_MT_BRIDGE_TOKEN not configured on server")
    if (token or "").strip() != expected:
        raise PermissionError("Invalid bridge token")


BRIDGE_FILES = ("jm_status.csv", "jm_ticks.csv", "jm_positions.csv", "jm_ack.csv")
COMMAND_FILE = "jm_command.csv"
