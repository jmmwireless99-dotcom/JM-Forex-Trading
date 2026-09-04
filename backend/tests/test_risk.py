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


def test_daily_loss_hit_disabled_by_default():
    risk = RiskManager(Settings())
    risk.record_realized_pnl(-1_000_000.0)
    assert risk.daily_loss_hit() is False


def test_daily_loss_hit_triggers_at_threshold():
    risk = RiskManager(Settings(max_daily_loss_pct=2.0))
    risk.reset_daily(10_000)
    assert risk.daily_loss_hit() is False
    risk.record_realized_pnl(-150.0)
    assert risk.daily_loss_hit() is False
    risk.record_realized_pnl(-60.0)
    assert risk.daily_loss_hit() is True


def test_evaluate_rejects_once_daily_loss_hit():
    risk = RiskManager(Settings(max_daily_loss_pct=1.0))
    risk.reset_daily(10_000)
    risk.record_realized_pnl(-150.0)
    tick = Tick(symbol="EURUSD", bid=1.1, ask=1.1001, mid=1.10005)
    decision = risk.evaluate(
        OrderRequest(symbol="EURUSD", side=Side.BUY, lots=0.1),
        balance=9_850,
        open_positions=[],
        tick=tick,
    )
    assert decision.approved is False
    assert "daily loss" in decision.reason.lower()