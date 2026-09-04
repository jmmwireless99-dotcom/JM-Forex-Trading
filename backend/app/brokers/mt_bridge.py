"""Unified MetaTrader 4/5 file bridge (same CSV protocol)."""

from __future__ import annotations

from app.brokers.mt4_bridge import BridgeAck, MT4FileBridge, _bridge_timeouts

# Alias — MT4 and MT5 EAs share the same file contract
MetaTraderBridge = MT4FileBridge


def _resolve_mt_symbol(settings, *, mode: str) -> str:
    mt5_path = getattr(settings, "mt5_bridge_dir", "") or ""
    remote = bool(getattr(settings, "mt_remote_bridge", False))
    if mt5_path or remote or mode == "mt5":
        return getattr(settings, "mt_symbol", None) or "GOLD#"
    return getattr(settings, "mt4_symbol", None) or "GOLD"


def resolve_platform_bridge(
    settings, platform: str
) -> tuple[MetaTraderBridge | None, str]:
    """Return (bridge, platform) for mt4 or mt5 independently."""
    platform = (platform or "mt5").lower()
    desk_symbol = settings.symbols[0] if settings.symbols else "XAUUSD"
    remote = bool(getattr(settings, "mt_remote_bridge", False))
    remote_cfg, online_max_age, order_timeout, ack_poll = _bridge_timeouts(settings)

    if platform == "mt4":
        path = getattr(settings, "mt4_bridge_dir", "") or ""
        mt_symbol = getattr(settings, "mt4_symbol", None) or "GOLD"
    elif platform == "mt4_real":
        path = getattr(settings, "mt4_real_bridge_dir", "") or ""
        mt_symbol = getattr(settings, "mt4_symbol", None) or "GOLD"
    else:
        path = getattr(settings, "mt5_bridge_dir", "") or ""
        mt_symbol = getattr(settings, "mt_symbol", None) or "GOLD#"

    if not path and not (remote and platform == "mt5"):
        return None, platform

    if not path:
        return None, platform

    bridge = MetaTraderBridge(
        path,
        symbol=mt_symbol,
        desk_symbol=desk_symbol,
        remote_mode=remote_cfg,
        online_max_age=online_max_age,
        order_timeout=order_timeout,
        ack_poll_seconds=ack_poll,
    )
    return bridge, platform


def resolve_mt_bridge(settings) -> tuple[MetaTraderBridge | None, str]:
    """Return (bridge, platform) where platform is mt4|mt5|paper."""
    mode = (getattr(settings, "execution_mode", "paper") or "paper").lower()
    mt_symbol = _resolve_mt_symbol(settings, mode=mode)
    desk_symbol = settings.symbols[0] if settings.symbols else "XAUUSD"
    remote = bool(getattr(settings, "mt_remote_bridge", False))

    remote_cfg, online_max_age, order_timeout, ack_poll = _bridge_timeouts(settings)

    def _bridge(path: str) -> MetaTraderBridge:
        return MetaTraderBridge(
            path,
            symbol=mt_symbol,
            desk_symbol=desk_symbol,
            remote_mode=remote_cfg,
            online_max_age=online_max_age,
            order_timeout=order_timeout,
            ack_poll_seconds=ack_poll,
        )

    if mode == "mt5":
        path = getattr(settings, "mt5_bridge_dir", "") or getattr(settings, "mt4_bridge_dir", "")
        if path or remote:
            if remote and path:
                from app.brokers.remote_bridge import ensure_remote_bridge_dir

                ensure_remote_bridge_dir(settings)
            if path:
                return _bridge(path), "mt5"
        return None, "mt5"

    if mode == "mt4":
        path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
        if path:
            return _bridge(path), "mt4"
        return None, "mt4"

    # Auto-detect configured folder even in paper (for status UI)
    path = getattr(settings, "mt4_bridge_dir", "") or getattr(settings, "mt5_bridge_dir", "")
    if path:
        platform = "mt5" if getattr(settings, "mt5_bridge_dir", "") or remote else "paper"
        return _bridge(path), platform
    return None, "paper"


__all__ = [
    "BridgeAck",
    "MetaTraderBridge",
    "MT4FileBridge",
    "resolve_mt_bridge",
    "resolve_platform_bridge",
]
