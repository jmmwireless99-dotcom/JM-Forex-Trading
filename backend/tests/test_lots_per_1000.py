"""Balance-scaled lot size: 0.5 lot per $1000."""

from app.core.config import Settings
from app.models.domain import OrderRequest, Side, Tick
from app.risk.manager import RiskManager


def test_lots_for_balance_scales_half_lot_per_thousand():
    risk = RiskManager(Settings(lots_per_1000=0.5))
    assert risk.lots_for_balance(1000) == 0.5
    assert risk.lots_for_balance(2000) == 1.0
    assert risk.lots_for_balance(500) == 0.25
    assert risk.lots_for_balance(10000) == 5.0


def test_lots_for_balance_clamps():
    risk = RiskManager(Settings(lots_per_1000=0.5))
    assert risk.lots_for_balance(0) == 0.01
    assert risk.lots_for_balance(200) == 0.1
    assert risk.lots_for_balance(100_000) == 10.0


def test_evaluate_uses_balance_lots_when_not_honoring():
    risk = RiskManager(Settings(lots_per_1000=0.5))
    tick = Tick(symbol="XAUUSD", bid=4100.0, ask=4100.2, mid=4100.1)
    decision = risk.evaluate(
        OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=10.0, strategy="EMA_RSI_Scalp"),
        balance=1000,
        open_positions=[],
        tick=tick,
    )
    assert decision.approved
    assert decision.adjusted_lots == 0.5


def test_honor_manual_lots_still_wins():
    risk = RiskManager(Settings(lots_per_1000=0.5))
    decision = risk.evaluate(
        OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.08, strategy="manual"),
        balance=1000,
        open_positions=[],
        tick=None,
        honor_requested_lots=True,
    )
    assert decision.approved
    assert decision.adjusted_lots == 0.08
