from datetime import datetime, timezone
from pathlib import Path

from app.ai.advisor import TradeAdvisor
from app.ai.features import parse_soft_confirm, vectorize
from app.models.domain import Side, Signal, TradeLog, TradeStatus


def test_soft_confirm_parser():
    assert parse_soft_confirm("EMA_RSI BUY · RSI 45 · soft") is True
    assert parse_soft_confirm("EMA_RSI BUY · RSI 45 · engulf") is False


def test_asia_soft_setup_is_caution_not_hard_skip(tmp_path: Path):
    """Asia reclaim/soft path must clear the CAUTION floor so AI_ML can trade."""
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
        reason="EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · RSI 45 · reclaim",
        stop_loss=4370.0,
        take_profit=4450.0,
        timestamp=datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc),
    )
    advice = advisor.advise_signal(signal, entry=4395.0)
    assert advice.action in {"TAKE", "CAUTION"}
    assert advice.win_probability >= 0.40
    assert advisor.should_block(advice) is False
    assert advice.source == "AI & Machine Learning"


def test_literal_soft_confirm_still_penalized(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=True,
        min_win_prob=0.4,
    )
    soft = Signal(
        strategy="EMA_RSI_Scalp",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.85,
        reason="EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · RSI 45 · soft",
        stop_loss=4370.0,
        take_profit=4450.0,
        timestamp=datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc),
    )
    reclaim = soft.model_copy(
        update={"reason": "EMA_RSI BUY · trend>EMA200 · retest EMA20/50 · RSI 45 · reclaim"}
    )
    soft_p = advisor.advise_signal(soft, entry=4395.0).win_probability
    reclaim_p = advisor.advise_signal(reclaim, entry=4395.0).win_probability
    assert reclaim_p > soft_p


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


def _smc_sell_overlap_signal() -> Signal:
    return Signal(
        strategy="Liquidity_Sweep_SMC",
        symbol="XAUUSD",
        side=Side.SELL,
        strength=0.9,
        reason="SMC SELL · ASIAN_HIGH sweep · engulf",
        stop_loss=4441.67,
        take_profit=4401.68,
        timestamp=datetime(2026, 8, 12, 13, 10, tzinfo=timezone.utc),
    )


def test_smc_sell_overlap_allowed_on_cold_start(tmp_path: Path):
    """Cold-start must not freeze overlap — only weak WR after enough samples."""
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=True,
        block_smc_sell_overlap=True,
        smc_sell_overlap_min_n=5,
        smc_sell_overlap_min_wr=0.35,
    )
    advice = advisor.advise_signal(_smc_sell_overlap_signal(), entry=4428.34)
    assert not any("cold-start" in r for r in advice.reasons)
    assert not any(r.startswith("Safety:") for r in advice.reasons)
    assert advice.action in {"TAKE", "CAUTION"}
    assert advisor.should_block(advice) is False


def test_smc_buy_overlap_never_hit_by_sell_safety(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=True,
        block_smc_sell_overlap=True,
    )
    buy = Signal(
        strategy="Liquidity_Sweep_SMC",
        symbol="XAUUSD",
        side=Side.BUY,
        strength=0.9,
        reason="SMC BUY · ASIAN_LOW sweep · MSS · FVG entry",
        stop_loss=4385.0,
        take_profit=4430.0,
        timestamp=datetime(2026, 8, 12, 13, 10, tzinfo=timezone.utc),
    )
    advice = advisor.advise_signal(buy, entry=4400.0)
    assert not any(r.startswith("Safety:") for r in advice.reasons)
    assert advice.action in {"TAKE", "CAUTION"}


def test_smc_sell_overlap_blocked_after_weak_wr(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=True,
        block_smc_sell_overlap=True,
        smc_sell_overlap_min_n=5,
        smc_sell_overlap_min_wr=0.35,
    )
    # Seed 5 losing SMC SELL overlap trades (same pattern as overnight SL cluster).
    for i in range(5):
        open_row = TradeLog(
            ticket=f"sl-{i}",
            symbol="XAUUSD",
            side=Side.SELL,
            lots=0.01,
            entry=4428.0,
            stop_loss=4441.0,
            take_profit=4401.0,
            status=TradeStatus.OPEN,
            strategy="Liquidity_Sweep_SMC",
            comment="SMC SELL · ASIAN_HIGH sweep",
            opened_at=datetime(2026, 8, 12, 13, 5 + i, tzinfo=timezone.utc),
        )
        advisor.record_open_from_trade(open_row, account_id="acc1")
        closed = open_row.model_copy(
            update={
                "status": TradeStatus.CLOSED,
                "exit": 4441.0,
                "realized_pnl": -53.0,
                "close_reason": "stop_loss",
                "closed_at": datetime(2026, 8, 12, 13, 20 + i, tzinfo=timezone.utc),
            }
        )
        advisor.record_close_from_trade(closed)

    bucket = advisor.store.bucket_stats(strategy="smc", side="SELL", session="overlap")
    assert bucket["n"] == 5
    assert bucket["win_rate"] == 0.0

    advice = advisor.advise_signal(_smc_sell_overlap_signal(), entry=4428.34)
    assert advice.action == "SKIP"
    assert advisor.should_block(advice) is True
    assert any("Safety" in r and "WR" in r for r in advice.reasons)


def test_smc_sell_overlap_safety_can_disable(tmp_path: Path):
    advisor = TradeAdvisor(
        history_path=str(tmp_path / "hist.jsonl"),
        model_path=str(tmp_path / "model.json"),
        enabled=True,
        gate_entries=False,
        block_smc_sell_overlap=False,
    )
    advice = advisor.advise_signal(_smc_sell_overlap_signal(), entry=4428.34)
    assert not any(r.startswith("Safety:") for r in advice.reasons)


def test_poisoned_model_heals_on_load(tmp_path: Path):
    import json
    from app.ai.model import OnlineLogisticModel

    path = tmp_path / "poison.json"
    path.write_text(
        json.dumps(
            {
                "name": "AI & Machine Learning",
                "backend": "sklearn",
                "weights": {
                    "bias": -1.05,
                    "side_buy": -1.05,
                    "sess_asia": -1.05,
                },
                "samples_seen": 43,
                "lr": 0.12,
                "l2": 0.01,
                "metrics": {},
            }
        )
    )
    model = OnlineLogisticModel(path=str(path))
    assert model.weights["bias"] > 0
    assert model.samples_seen == 0
    assert (model.last_metrics or {}).get("note") == "reset_poisoned_weights"
