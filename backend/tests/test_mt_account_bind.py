"""MT-bound JM FX client accounts mirror live terminal; others stay paper."""

import pytest

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import get_remote_mt_state, remote_push
from app.core.config import Settings
from app.engine.trading_engine import TradingEngine
from app.models.domain import OrderRequest, Side, Tick, utcnow
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


def _engine(tmp_path, *, online: bool = True):
    _reset_store()
    if online:
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
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "acc.json")
    return engine


def test_bound_account_uses_mt_balance(tmp_path):
    engine = _engine(tmp_path, online=True)
    acct = engine.accounts.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.bind@gmail.com",
        mt5_login="25817283",
        password="secret12",
        deposit=1000,
    )

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
    engine = _engine(tmp_path, online=False)
    acct = engine.accounts.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.bind2@gmail.com",
        mt5_login="25817299",
        password="secret12",
        deposit=1000,
    )
    assert engine.is_mt5_client(acct) is True
    assert engine.is_mt_bound(acct) is False
    payload = engine.account_payload(acct)
    assert payload["paper"] is False
    assert payload["balance"] == 0.0
    assert payload["deposit"] == 0.0
    assert payload["binding"] == "waiting_mt5"
    assert payload["mt_bound"] is False


def test_paper_account_stays_paper_when_mt5_mode_online(tmp_path):
    engine = _engine(tmp_path, online=True)
    paper = engine.accounts.create(
        label="Demo Friend",
        deposit=1500,
        password="secret12",
    )
    assert paper.mt5_login == ""
    assert engine.is_mt5_client(paper) is False
    assert engine.is_mt_bound(paper) is False
    assert engine.uses_paper_book(paper) is True
    payload = engine.account_payload(paper)
    assert payload["binding"] == "paper"
    assert payload["balance"] == 1500.0
    assert payload["deposit"] == 1500.0


def test_other_mt5_login_not_bound_to_joel_terminal(tmp_path):
    engine = _engine(tmp_path, online=True)
    other = engine.accounts.create(
        first_name="Other",
        last_name="Client",
        email="other.client@gmail.com",
        mt5_login="99999999",
        password="secret12",
    )
    assert engine.is_mt5_client(other) is True
    assert engine.is_mt_bound(other) is False
    payload = engine.account_payload(other)
    assert payload["binding"] == "waiting_mt5"
    assert payload["balance"] == 0.0


def test_no_login_in_status_binds_nobody(tmp_path):
    _reset_store()
    remote_push(
        status_csv="ok,2500.50,2510.00,0,2026.07.23 11:00:00\n",
        ticks_csv="XAUUSD,4090.10,4090.40,2026.07.23 11:00:00\n",
        positions_csv="",
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
    engine.accounts = PaperAccountRegistry(settings, store_path=tmp_path / "nologin.json")
    joel = engine.accounts.create(
        first_name="Joel",
        last_name="Madera",
        email="joel.nologin@gmail.com",
        mt5_login="25817283",
        password="secret12",
    )
    assert engine.connected_mt_login() in (None, "")
    assert engine.is_mt_bound(joel) is False


@pytest.mark.asyncio
async def test_paper_fill_works_while_global_mode_mt5_offline(tmp_path):
    engine = _engine(tmp_path, online=False)
    paper = engine.accounts.create(
        label="Paper Only",
        deposit=2000,
        password="secret12",
    )
    tick = Tick(
        symbol="XAUUSD",
        bid=2350.0,
        ask=2350.2,
        mid=2350.1,
        timestamp=utcnow(),
    )
    paper.broker._last_ticks["XAUUSD"] = tick
    engine._recent_ticks["XAUUSD"] = tick

    order = await engine._execute(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            strategy="manual",
            comment="paper ok",
        ),
        tick=tick,
        account=paper,
    )
    assert order.status.value == "FILLED"
    assert paper.broker.snapshot().open_positions == 1
