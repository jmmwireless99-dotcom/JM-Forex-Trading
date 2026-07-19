from app.brokers.paper import PaperBroker
from app.models.domain import OrderRequest, Side, Tick


def test_market_fill_and_pnl():
    broker = PaperBroker(initial_balance=10_000)
    broker.update_tick(Tick(symbol="EURUSD", bid=1.1000, ask=1.1002, mid=1.1001))
    order = broker.place_order(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=0.1, stop_loss=1.09, take_profit=1.12)
    )
    assert order.status.value == "FILLED"
    assert len(broker.open_positions()) == 1

    # Price moves up → profit on long
    broker.update_tick(Tick(symbol="EURUSD", bid=1.1010, ask=1.1012, mid=1.1011))
    pos = broker.open_positions()[0]
    assert pos.unrealized_pnl > 0

    closed = broker.close_position(pos.id)
    assert closed is not None
    assert closed.realized_pnl > 0
    assert broker.balance > 10_000


def test_stop_loss_triggers():
    broker = PaperBroker()
    broker.update_tick(Tick(symbol="EURUSD", bid=1.1000, ask=1.1002, mid=1.1001))
    broker.place_order(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=0.1, stop_loss=1.0990, take_profit=1.12)
    )
    closed = broker.update_tick(Tick(symbol="EURUSD", bid=1.0985, ask=1.0987, mid=1.0986))
    assert len(closed) == 1
    assert closed[0].close_reason == "stop_loss"
    assert len(broker.open_positions()) == 0