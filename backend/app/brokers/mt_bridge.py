"""Unified MetaTrader 4/5 file bridge (same CSV protocol)."""

from __future__ import annotations

from app.brokers.mt4_bridge import BridgeAck, MT4FileBridge

# Alias — MT4 and MT5 EAs share the same file contract
MetaTraderBridge = MT4FileBridge


def resolve_mt_bridge(settings) -> tuple[MetaTraderBridge | None, str]:
    """Return (bridge, platform) where platform is mt4|mt5|paper."""
    mode = (getattr(settings, "execution_mode", "paper") or "paper").lower()
    symbol = getattr(settings, "mt4_symbol", None) or getattr(settings, "mt_symbol", "XAUUSD")

    if mode == "mt5":
        path = getattr(settings, "mt5_bridge_dir", "") or getattr(settings, "mt4_bridge_dir", "")
        if path:
            return MetaTraderBridge(path, symbol=symbol), "mt5"
        return None, "mt5"

    if mode == "mt4":
        path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
        if path:
            return MetaTraderBridge(path, symbol=symbol), "mt4"
        return None, "mt4"

    # Auto-detect configured folder even in paper (for status UI)
    path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
    if path:
        return MetaTraderBridge(path, symbol=symbol), "paper"
    return None, "paper"


__all__ = ["BridgeAck", "MetaTraderBridge", "MT4FileBridge", "resolve_mt_bridge"]
