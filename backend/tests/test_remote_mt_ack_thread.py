"""Remote MT bridge must accept EA acks while waiting (no event-loop deadlock)."""

from __future__ import annotations

import asyncio
import threading
import time

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import get_remote_mt_state, remote_push


def _reset(plat: str = "mt5") -> None:
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


def test_ping_ack_while_waiting_in_thread():
    """Simulate agent push of ack while bridge.ping waits in a worker thread."""
    _reset("mt5")
    remote_push(
        platform="mt5",
        status_csv="ok,2000,2000,0,2026.07.24 00:00:00,25817283\n",
        ticks_csv="XAUUSD,4040,4040.3,2026.07.24 00:00:00\n",
        agent_host="test",
    )
    bridge = RemoteMetaTraderBridge(platform="mt5")

    def deliver_ack() -> None:
        # Wait until command is queued, then push EA ack (like Windows agent).
        for _ in range(50):
            st = get_remote_mt_state("mt5")
            with st.lock:
                cmd_id = st.pending_command_id
            if cmd_id:
                remote_push(
                    platform="mt5",
                    status_csv="ok,2000,2000,0,2026.07.24 00:00:00,25817283\n",
                    ack_csv=f"{cmd_id},OK,pong\n",
                    agent_host="test",
                )
                return
            time.sleep(0.05)

    t = threading.Thread(target=deliver_ack, daemon=True)
    t.start()
    ack = bridge.ping(timeout=5.0)
    t.join(timeout=2)
    assert ack.ok is True
    assert ack.detail == "pong"


def test_async_route_style_to_thread_ping():
    """Mirrors FastAPI: await asyncio.to_thread(bridge.ping) + concurrent push."""
    _reset("mt5")
    remote_push(
        platform="mt5",
        status_csv="ok,2000,2000,0,2026.07.24 00:00:00,25817283\n",
        ticks_csv="XAUUSD,4040,4040.3,2026.07.24 00:00:00\n",
        agent_host="test",
    )
    bridge = RemoteMetaTraderBridge(platform="mt5")

    async def run() -> None:
        async def pusher() -> None:
            for _ in range(40):
                st = get_remote_mt_state("mt5")
                with st.lock:
                    cmd_id = st.pending_command_id
                if cmd_id:
                    remote_push(
                        platform="mt5",
                        status_csv="ok,2000,2000,0,2026.07.24 00:00:00,25817283\n",
                        ack_csv=f"{cmd_id},OK,pong\n",
                        agent_host="test",
                    )
                    return
                await asyncio.sleep(0.05)

        push_task = asyncio.create_task(pusher())
        ack = await asyncio.to_thread(bridge.ping, 5.0)
        await push_task
        assert ack.ok is True

    asyncio.run(run())
