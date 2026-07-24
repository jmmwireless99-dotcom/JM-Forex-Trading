"""Tests for cloud ↔ Windows remote MT bridge."""

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import (
    get_remote_mt_state,
    remote_push,
    remote_set_command,
)
from app.models.domain import Side


def _reset_store():
    for plat in ("mt4", "mt5"):
        st = get_remote_mt_state(plat)
        with st.lock:
            st.status_csv = ""
            st.ticks_csv = ""
            st.positions_csv = ""
            st.ack_csv = ""
            st.last_push_at = 0.0
            st.mt_login = ""
            st.pending_command_csv = ""
            st.pending_command_id = ""


def test_remote_bridge_online_and_tick():
    _reset_store()
    remote_push(
        status_csv="ok,1000.00,1005.00,0,2026.07.23 10:00:00\n",
        ticks_csv="XAUUSD,4090.10,4090.40,2026.07.23 10:00:00\n",
        positions_csv="ticket,symbol,side,lots,open_price,sl,tp,profit\n",
        symbol="XAUUSD",
        agent_host="test-pc",
        platform="mt5",
    )
    bridge = RemoteMetaTraderBridge(symbol="XAUUSD", platform="mt5")
    assert bridge.is_online(max_age_seconds=30) is True
    tick = bridge.read_tick()
    assert tick is not None
    assert tick.bid == 4090.10
    snap = bridge.snapshot()
    assert snap.balance == 1000.0
    assert snap.equity == 1005.0


def test_remote_bridge_place_order_ack(monkeypatch):
    _reset_store()
    remote_push(
        status_csv="ok,1000.00,1000.00,0,2026.07.23 10:00:00\n",
        ticks_csv="XAUUSD,4090.10,4090.40,2026.07.23 10:00:00\n",
        symbol="XAUUSD",
        agent_host="test-pc",
        platform="mt5",
    )
    bridge = RemoteMetaTraderBridge(symbol="XAUUSD", platform="mt5")

    original_set = remote_set_command

    def set_and_ack(command_id: str, csv_payload: str, platform: str | None = "mt5"):
        original_set(command_id, csv_payload, platform=platform)
        st = get_remote_mt_state(platform)
        with st.lock:
            st.ack_csv = f"{command_id},OK,555\n"

    monkeypatch.setattr(
        "app.brokers.remote_mt_bridge.remote_set_command",
        set_and_ack,
    )

    from app.models.domain import OrderRequest

    order = bridge.place_order(
        OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.01, comment="test"),
        timeout=2.0,
    )
    assert order.status.value == "FILLED"
    assert "555" in (order.comment or "")
