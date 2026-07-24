"""Unified MetaTrader 4/5 bridge (local file folder or remote Windows agent)."""

from __future__ import annotations

from app.brokers.mt4_bridge import BridgeAck, MT4FileBridge
from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge

# Alias — MT4 and MT5 EAs share the same file contract
MetaTraderBridge = MT4FileBridge | RemoteMetaTraderBridge


def resolve_mt_bridge(settings) -> tuple[MetaTraderBridge | None, str]:
    """Return (primary bridge, platform) where platform is mt4|mt5|paper.

    When remote bridge is on, primary follows execution_mode but both platforms
    are available via TradingEngine.bridges.
    """
    mode = (getattr(settings, "execution_mode", "paper") or "paper").lower()
    symbol = getattr(settings, "mt4_symbol", None) or getattr(settings, "mt_symbol", "XAUUSD")
    remote_on = bool(getattr(settings, "mt_remote_bridge", False))

    if mode == "mt5":
        if remote_on:
            return RemoteMetaTraderBridge(symbol=symbol, platform="mt5"), "mt5"
        path = getattr(settings, "mt5_bridge_dir", "") or getattr(settings, "mt4_bridge_dir", "")
        if path:
            return MT4FileBridge(path, symbol=symbol), "mt5"
        return None, "mt5"

    if mode == "mt4":
        if remote_on:
            return RemoteMetaTraderBridge(symbol=symbol, platform="mt4"), "mt4"
        path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
        if path:
            return MT4FileBridge(path, symbol=symbol), "mt4"
        return None, "mt4"

    # Auto-detect configured folder even in paper (for status UI)
    if remote_on:
        return RemoteMetaTraderBridge(symbol=symbol, platform="mt5"), "paper"
    path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
    if path:
        return MT4FileBridge(path, symbol=symbol), "paper"
    return None, "paper"


def resolve_dual_remote_bridges(settings) -> dict[str, RemoteMetaTraderBridge]:
    """Always-on MT4 + MT5 remote bridges when JM_MT_REMOTE_BRIDGE=true."""
    if not bool(getattr(settings, "mt_remote_bridge", False)):
        return {}
    symbol = getattr(settings, "mt4_symbol", None) or getattr(settings, "mt_symbol", "XAUUSD")
    return {
        "mt4": RemoteMetaTraderBridge(symbol=symbol, platform="mt4"),
        "mt5": RemoteMetaTraderBridge(symbol=symbol, platform="mt5"),
    }


__all__ = [
    "BridgeAck",
    "MetaTraderBridge",
    "MT4FileBridge",
    "RemoteMetaTraderBridge",
    "resolve_mt_bridge",
    "resolve_dual_remote_bridges",
]
