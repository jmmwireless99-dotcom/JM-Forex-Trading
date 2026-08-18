from datetime import datetime, timezone
from pathlib import Path

from app.ai.advisor import TradeAdvisor
from app.ai.aiml_strategy import AIMLStrategy
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies import STRATEGY_REGISTRY, create_strategy
from app.strategies.auto_router import AutoStrategyRouter


def test_aiml_registered():
    assert "AI_ML" in STRATEGY_REGISTRY
    strat = create_strategy("AI_ML")
    assert strat.name == "AI_ML"
    assert strat.candle_driven is True


def test_auto_router_parks_aiml():
    router = AutoStrategyRouter()
    ts = datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc)
    decision = router.decide(ts, [4400.0] * 30)
    assert decision.allow_trading is True
    assert decision.strategy == "AI_ML"
    assert decision.child_strategy == "EMA_RSI_Scalp"


def test_aiml_blocks_skip_from_ml(tmp_path: Path, monkeypatch):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "h.jsonl"),
        model_path=str(tmp_path / "m.json"),
        enabled=True,
        gate_entries=False,
    )
    strat = AIMLStrategy()
    strat.set_advisor(advisor)

    # Force Asia child path and a soft-confirm signal the ML priors dislike.
    child_signal = Signal(
        strategy="EMA_RSI_Scalp",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.85,
        reason="EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · RSI 45 · soft",
        stop_loss=4370.0,
        take_profit=4450.0,
        timestamp=datetime(2026, 8, 12, 3, 5, tzinfo=timezone.utc),
    )

    class _Stub:
        candle_driven = True
        last_checklist = ["stub"]
        last_block_reason = None

        def set_structure_bars(self, candles):
            return None

        def on_bar(self, candles, tick):
            return child_signal

        def evaluate(self, tick):
            return None

    strat._children["EMA_RSI_Scalp"] = _Stub()  # type: ignore[assignment]
    tick = Tick(
        symbol="XAUUSD",
        bid=4394.9,
        ask=4395.1,
        mid=4395.0,
        timestamp=datetime(2026, 8, 12, 3, 5, tzinfo=timezone.utc),
    )
    bars = [
        Candle(
            symbol="XAUUSD",
            open=4390,
            high=4396,
            low=4388,
            close=4395,
            volume=1,
            period_seconds=300,
            open_time=datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc),
            timestamp=datetime(2026, 8, 12, 3, 5, tzinfo=timezone.utc),
            is_closed=True,
        )
    ]
    out = strat.on_bar(bars, tick)
    assert out is None
    assert strat.last_block_reason and "AI_ML SKIP" in strat.last_block_reason
