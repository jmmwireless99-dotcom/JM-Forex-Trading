"""Broker history CSV must drive JM FX MT journal PnL (not tick.mid guess)."""

from datetime import datetime, timezone

from app.brokers.remote_mt_bridge import RemoteMetaTraderBridge
from app.brokers.remote_mt_store import get_remote_mt_state, remote_push
from app.engine.trade_journal import TradeJournal
from app.models.domain import Side, TradeStatus


def _reset(plat: str = "mt4") -> None:
    st = get_remote_mt_state(plat)
    with st.lock:
        st.status_csv = ""
        st.ticks_csv = ""
        st.positions_csv = ""
        st.history_csv = ""
        st.ack_csv = ""
        st.last_push_at = 0.0


def test_closed_history_parses_broker_profit():
    _reset("mt4")
    remote_push(
        status_csv="ok,977.30,977.30,0,2026.07.24 22:00:00,893283499,1,\n",
        ticks_csv="XAUUSD,4050.00,4050.30,2026.07.24 22:00:00\n",
        positions_csv="ticket,symbol,side,lots,open_price,sl,tp,profit\n",
        history_csv=(
            "ticket,symbol,side,lots,open_price,close_price,sl,tp,profit,close_time\n"
            "418000323,XAUUSD,BUY,0.01,4075.63,4073.10,4072.00,4080.00,-2.85,2026.07.24 18:01:00\n"
        ),
        platform="mt4",
        agent_host="test",
        symbol="XAUUSD",
    )
    bridge = RemoteMetaTraderBridge(symbol="XAUUSD", platform="mt4")
    hist = bridge.closed_history()
    assert "418000323" in hist
    assert hist["418000323"]["profit"] == -2.85
    assert hist["418000323"]["close_price"] == 4073.10
    assert hist["418000323"]["lots"] == 0.01


def test_apply_broker_close_corrects_estimated_pnl():
    journal = TradeJournal()
    # Fake an estimated close (old bug path)
    from app.models.domain import TradeLog

    row = TradeLog(
        ticket="418000323",
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.01,
        entry=4075.63,
        status=TradeStatus.CLOSED,
        realized_pnl=-22.61,
        exit=4053.02,
        close_reason="mt_closed_synced",
        mode="paper",
        closed_at=datetime(2026, 7, 24, 18, 1, tzinfo=timezone.utc),
    )
    journal._trades.appendleft(row)
    journal._by_ticket[row.ticket] = row

    fixed = journal.apply_broker_close(
        "418000323",
        exit_price=4073.10,
        realized_pnl=-2.85,
        lots=0.01,
        entry=4075.63,
        close_reason="mt_broker_close",
        mode="mt4",
    )
    assert fixed is not None
    assert fixed.realized_pnl == -2.85
    assert fixed.exit == 4073.10
    assert fixed.mode == "mt4"
    assert fixed.close_reason == "mt_broker_close"
    assert fixed.status == TradeStatus.CLOSED
