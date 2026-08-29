"""Server-side bridge folder updated by the Windows PC sync agent."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def remote_bridge_dir(settings: Settings, platform: str = "mt5") -> Path | None:
    """Directory where the PC agent / EA writes jm_*.csv copies."""
    if not settings.mt_remote_bridge:
        return None
    platform = (platform or "mt5").lower()
    if platform == "mt4":
        path = (settings.mt4_bridge_dir or "").strip()
    elif platform == "mt4_real":
        path = (settings.mt4_real_bridge_dir or "").strip()
    else:
        path = (settings.mt5_bridge_dir or settings.mt4_bridge_dir or "").strip()
    if not path:
        return None
    return Path(path)


def ensure_remote_bridge_dir(settings: Settings, platform: str = "mt5") -> Path:
    root = remote_bridge_dir(settings, platform=platform)
    if root is None:
        label = {
            "mt4": "JM_MT4_BRIDGE_DIR",
            "mt4_real": "JM_MT4_REAL_BRIDGE_DIR",
        }.get(platform, "JM_MT5_BRIDGE_DIR")
        raise ValueError(f"JM_MT_REMOTE_BRIDGE requires {label}")
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
