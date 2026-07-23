"""MT-bound JM FX client accounts mirror live terminal balance/positions."""

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import get_remote_mt_state, remote_push
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.paper_accounts.registry import PaperAccountRegistry


def _reset_store():
    st = get_remote_mt_state()
    with st.lock:
        st.status_csv = ""
        st.ticks_csv = ""
        st.positions_csv = ""
        st.ack_csv = ""
        st.last_push_at = 0.0
        st.mt_login = ""
        st.pending_command_csv = ""
        st.pending_command_id = ""


def test_bound_account_uses_mt_balance(tmp_path):
    _reset_store()
    remote_push(
        status_csv="ok,2500.50,2510.00,1,2026.07.23 11:00:00,25817283\n",
        ticks_csv="XAUUSD,4090.10,4090.40,2026.07.23 11:00:00\n",
        positions_csv=(
            "ticket,symbol,side,lots,open_price,sl,tp,profit\n"
            "99,XAUUSD,BUY,0.02,4090.00,4080.00,4110.00,5.50\n"
        ),
        symbol="XAUUSD",
        agent_host="test-pc",
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
    engine.mode = "mt5"
    engine.mt = RemoteMetaTraderBridge(symbol="XAUUSD")
    engine._mt_platform = "mt5"

    registry = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")
    acct = registry.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.bind@gmail.com",
        mt5_login="25817283",
        password="secret12",
        deposit=1000,
    )
    engine.accounts = registry

    assert engine.is_mt_bound(acct) is True
    payload = engine.account_payload(acct)
    assert payload["mt_bound"] is True
    assert payload["paper"] is False
    assert payload["balance"] == 2500.50
    assert payload["equity"] == 2510.00
    assert payload["mt5_login"] == "25817283"
    opens = engine.open_positions(acct)
    assert len(opens) == 1
    assert opens[0].lots == 0.02


def test_mt5_client_offline_hides_paper_deposit(tmp_path):
    _reset_store()
    settings = Settings(
        tick_interval_seconds=0.05,
        auto_strategy=False,
        execution_mode="mt5",
        mt_remote_bridge=True,
        mt_bridge_token="test-token",
        paper_sync_live_gold=False,
    )
    engine = TradingEngine(settings)
    engine.mode = "mt5"
    engine.mt = RemoteMetaTraderBridge(symbol="XAUUSD")
    registry = PaperAccountRegistry(settings, store_path=tmp_path / "acc2.json")
    acct = registry.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.bind2@gmail.com",
        mt5_login="25817299",
        password="secret12",
        deposit=1000,
    )
    engine.accounts = registry
    assert engine.is_mt5_client(acct) is True
    assert engine.is_mt_bound(acct) is False
    payload = engine.account_payload(acct)
    assert payload["paper"] is False
    assert payload["balance"] == 0.0
    assert payload["deposit"] == 0.0
    assert payload["binding"] == "waiting_mt5"
    assert payload["mt_bound"] is False
