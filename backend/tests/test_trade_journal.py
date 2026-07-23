from app.engine.trade_journal import TradeJournal
from app.models.domain import Order, OrderStatus, Position, PositionStatus, Side


def test_journal_open_and_close_details():
    journal = TradeJournal()
    order = Order(
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.05,
        status=OrderStatus.FILLED,
        fill_price=2350.4,
        stop_loss=2340.0,
        take_profit=2370.0,
        strategy="gold_confluence",
        comment="trial",
    )
    pos = Position(
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.05,
        entry_price=2350.4,
        stop_loss=2340.0,
        take_profit=2370.0,
        strategy="gold_confluence",
    )
    row = journal.record_open_position(pos, mode="paper")
    assert row.status.value == "OPEN"
    assert row.entry == 2350.4
    assert row.stop_loss == 2340.0
    assert row.take_profit == 2370.0

    pos.status = PositionStatus.CLOSED
    pos.close_price = 2370.0
    pos.realized_pnl = 98.0
    pos.close_reason = "take_profit"
    closed = journal.record_close(pos)
    assert closed is not None
    assert closed.status.value == "CLOSED"
    assert closed.exit == 2370.0
    assert closed.realized_pnl == 98.0
    assert closed.close_reason == "take_profit"

    summary = journal.summary()
    assert summary["closed"] == 1
    assert summary["wins"] == 1


def test_journal_rejected_order():
    journal = TradeJournal()
    order = Order(
        symbol="XAUUSD",
        side=Side.SELL,
        lots=0.1,
        status=OrderStatus.REJECTED,
        stop_loss=2360.0,
        take_profit=2330.0,
        reject_reason="Max open positions reached",
    )
    row = journal.record_order(order)
    assert row.status.value == "REJECTED"
    assert row.reject_reason is not None
    assert journal.summary()["rejected"] == 1
