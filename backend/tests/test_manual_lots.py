"""Manual lot size honored for strategy fills."""

from app.core.config import Settings
from app.models.domain import OrderRequest, Side
from app.risk.manager import RiskManager


def test_honor_requested_lots_skips_risk_resize():
    risk = RiskManager(Settings(max_risk_per_trade_pct=0.5, default_stop_loss_pips=55))
    risk.reset_daily(1000)
    req = OrderRequest(symbol="XAUUSD", side=Side.BUY, lots=0.05, strategy="London_Judas_Sweep")
    # Tiny balance would normally force 0.01 — honor keeps 0.05
    decision = risk.evaluate(
        req,
        balance=100,
        open_positions=[],
        tick=None,
        honor_requested_lots=True,
    )
    assert decision.approved
    assert decision.adjusted_lots == 0.05
