from app.core.config import Settings
from app.models.domain import OrderRequest, Position, Side, Tick
from app.risk.manager import RiskManager


def test_rejects_zero_lots():
    risk = RiskManager(Settings())
    decision = risk.evaluate(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=0),
        balance=10_000,
        open_positions=[],
        tick=None,
    )
    assert decision.approved is False


def test_rejects_when_max_positions_reached():
    settings = Settings(max_open_positions=1)
    risk = RiskManager(settings)
    open_pos = [
        Position(symbol="GBPUSD", side=Side.BUY, lots=0.1, entry_price=1.26),
    ]
    decision = risk.evaluate(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=0.1),
        balance=10_000,
        open_positions=open_pos,
        tick=None,
    )
    assert decision.approved is False
    assert "Max open positions" in decision.reason


def test_allows_same_direction_pyramid_until_max():
    settings = Settings(max_open_positions=3)
    risk = RiskManager(settings)
    open_pos = [
        Position(symbol="XAUUSD", side=Side.BUY, lots=0.01, entry_price=4100.0),
    ]
    ok = risk.evaluate(
        OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.01, strategy="manual"),
        balance=10_000,
        open_positions=open_pos,
        tick=None,
        honor_requested_lots=True,
    )
    assert ok.approved is True

    bad = risk.evaluate(
        OrderRequest(symbol="XAUUSD", side=Side.SELL, lots=0.01, strategy="manual"),
        balance=10_000,
        open_positions=open_pos,
        tick=None,
        honor_requested_lots=True,
    )
    assert bad.approved is False
    assert "Opposite" in bad.reason


def test_approves_and_sizes_lots():
    risk = RiskManager(Settings(max_risk_per_trade_pct=1.0))
    tick = Tick(symbol="EURUSD", bid=1.1, ask=1.1001, mid=1.10005)
    decision = risk.evaluate(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=1.0),
        balance=10_000,
        open_positions=[],
        tick=tick,
    )
    assert decision.approved is True
    assert decision.adjusted_lots is not None
    assert decision.adjusted_lots <= 1.0