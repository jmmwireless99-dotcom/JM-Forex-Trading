from datetime import datetime, timezone
from pathlib import Path

from app.ai.advisor import TradeAdvisor
from app.ai.features import parse_soft_confirm, vectorize
from app.models.domain import Side, Signal, TradeLog, TradeStatus


def test_soft_confirm_parser():
    assert parse_soft_confirm("EMA_RSI BUY · RSI 45 · soft") is True
    assert parse_soft_confirm("EMA_RSI BUY · RSI 45 · engulf") is False


def test_asia_soft_setup_is_skipped(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=True,
        min_win_prob=0.4,
        skip_confidence=0.5,
    )
    signal = Signal(
        strategy="EMA_RSI_Scalp",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.85,
        reason="EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · RSI 45 · soft",
        stop_loss=4370.0,
        take_profit=4450.0,
        timestamp=datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc),
    )
    advice = advisor.advise_signal(signal, entry=4395.0)
    assert advice.action == "SKIP"
    assert advice.win_probability < 0.4
    assert advisor.should_block(advice) is True
    assert advice.source == "AI & Machine Learning"
    assert any("ML" in r or "probability" in r.lower() for r in advice.reasons)
    # Machine Learning coefficients should flag soft_confirm / sess_asia
    driver_names = {d["feature"] for d in advice.drivers}
    assert "soft_confirm" in driver_names or "sess_asia" in driver_names


def test_history_learn_from_close(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=False,
    )
    open_row = TradeLog(
        ticket="t1",
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.01,
        entry=4400.0,
        stop_loss=4385.0,
        take_profit=4430.0,
        status=TradeStatus.OPEN,
        strategy="EMA_RSI_Scalp",
        comment="EMA_RSI BUY · RSI 40 · soft",
        opened_at=datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc),
    )
    advisor.record_open_from_trade(open_row, account_id="acc1")
    closed = open_row.model_copy(
        update={
            "status": TradeStatus.CLOSED,
            "exit": 4385.0,
            "realized_pnl": -1.5,
            "close_reason": "stop_loss",
            "closed_at": datetime(2026, 8, 12, 4, 30, tzinfo=timezone.utc),
        }
    )
    labeled = advisor.record_close_from_trade(closed)
    assert labeled is not None
    assert labeled["label"] == 0
    stats = advisor.store.stats()
    assert stats["labeled"] == 1
    assert stats["losses"] == 1
    assert advisor.model.samples_seen >= 1


def test_vectorize_session_buckets():
    feats = vectorize(
        strategy="Liquidity_Sweep_SMC",
        side="SELL",
        reason="SMC SELL · engulf",
        ts=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        entry=4390.0,
        stop_loss=4410.0,
        take_profit=4350.0,
    )
    assert feats["strat_smc"] == 1.0
    assert feats["sess_overlap"] == 1.0
    assert feats["soft_confirm"] == 0.0
