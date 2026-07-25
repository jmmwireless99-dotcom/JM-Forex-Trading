"""Dual always-on MT4 + MT5 remote bridges bind per account."""

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import get_remote_mt_state, remote_push
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.paper_accounts.registry import PaperAccountRegistry


def _reset():
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


def test_joel_mt5_and_mt4_account_both_bound(tmp_path):
    _reset()
    remote_push(
        platform="mt5",
        status_csv="ok,2000.00,2000.00,0,2026.07.24 00:00:00,25817283\n",
        ticks_csv="XAUUSD,4040.00,4040.30,2026.07.24 00:00:00\n",
        positions_csv="",
        symbol="XAUUSD",
        agent_host="pc-mt5",
    )
    remote_push(
        platform="mt4",
        status_csv="ok,1000.00,1000.00,0,2026.07.24 00:00:00,893283499\n",
        ticks_csv="XAUUSD,4040.10,4040.40,2026.07.24 00:00:00\n",
        positions_csv="",
        symbol="XAUUSD",
        agent_host="pc-mt4",
    )

    settings = Settings(
        tick_interval_seconds=0.05,
        auto_strategy=False,
        execution_mode="mt5",
        mt_remote_bridge=True,
        mt_bridge_token="test-token",
        paper_sync_live_gold=False,
    )
    engine = TradingEngine(settings)
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")

    joel = engine.accounts.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.dual@gmail.com",
        mt5_login="25817283",
        mt_platform="mt5",
        password="secret12",
    )
    mt4 = engine.accounts.create(
        first_name="MT4",
        last_name="Live",
        email="mt4.dual@gmail.com",
        mt5_login="893283499",
        mt_platform="mt4",
        password="secret12",
    )

    assert engine.is_mt_bound(joel) is True
    assert engine.is_mt_bound(mt4) is True
    assert engine.account_payload(joel)["balance"] == 2000.0
    assert engine.account_payload(mt4)["balance"] == 1000.0
    assert engine.account_payload(joel)["binding"] == "live_mt5"
    assert engine.account_payload(mt4)["binding"] == "live_mt4"
    assert isinstance(engine.bridges["mt5"], RemoteMetaTraderBridge)
    assert engine.bridges["mt4"].is_online()


def test_profile_can_switch_account_to_mt4(tmp_path):
    _reset()
    settings = Settings(
        tick_interval_seconds=0.05,
        auto_strategy=False,
        execution_mode="mt5",
        mt_remote_bridge=True,
        mt_bridge_token="test-token",
        paper_sync_live_gold=False,
    )
    engine = TradingEngine(settings)
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")
    nonoy = engine.accounts.create(
        first_name="Nonoy",
        last_name="Madera",
        email="nonoy.dual@gmail.com",
        mt5_login="893283499",
        mt_platform="mt5",  # wrong at register — fix via profile
        password="secret12",
    )
    assert nonoy.mt_platform == "mt5"
    out = engine.update_client_profile(nonoy, mt_platform="mt4")
    assert nonoy.mt_platform == "mt4"
    assert out["account"]["mt_platform"] == "mt4"
