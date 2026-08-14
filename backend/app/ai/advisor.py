"""AI & Machine Learning decision layer — history + ML scoring only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.ai.features import (
    context_tags,
    features_from_signal,
    features_from_trade,
    session_bucket,
    vectorize,
)
from app.ai.history_store import TradeHistoryStore
from app.ai.model import OnlineLogisticModel
from app.models.domain import Signal, TradeLog


@dataclass
class Advice:
    action: str  # TAKE | CAUTION | SKIP
    win_probability: float
    confidence: float
    reasons: list[str]
    drivers: list[dict[str, Any]]
    context: dict[str, Any]
    model_samples: int
    gated: bool = False
    source: str = "AI & Machine Learning"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradeAdvisor:
    """AI & Machine Learning entry scoring backed by persistent trade history."""

    def __init__(
        self,
        *,
        history_path: str,
        model_path: str,
        enabled: bool = True,
        gate_entries: bool = False,
        min_win_prob: float = 0.40,
        skip_confidence: float = 0.55,
        block_smc_sell_overlap: bool = True,
        smc_sell_overlap_min_wr: float = 0.35,
        smc_sell_overlap_min_n: int = 5,
    ) -> None:
        self.enabled = enabled
        self.gate_entries = gate_entries
        self.min_win_prob = min_win_prob
        self.skip_confidence = skip_confidence
        self.block_smc_sell_overlap = block_smc_sell_overlap
        self.smc_sell_overlap_min_wr = smc_sell_overlap_min_wr
        self.smc_sell_overlap_min_n = smc_sell_overlap_min_n
        self.store = TradeHistoryStore(history_path)
        self.model = OnlineLogisticModel(path=model_path)
        # Train only on strategy-tagged desk setups — manual/other rows were
        # poisoning bias/side_buy/sess_asia and SKIPping every AI_ML child.
        labeled = [
            r
            for r in self.store.labeled()
            if (r.get("context") or {}).get("strategy")
            in {"ema_rsi", "smc", "judas", "vwap", "trend"}
        ]
        if labeled:
            self.model.fit_many(labeled, epochs=3)

    def advise_signal(
        self,
        signal: Signal,
        *,
        entry: float | None = None,
        session: str | None = None,
    ) -> Advice:
        sess = session or session_bucket(signal.timestamp)
        side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)
        feats = features_from_signal(signal, entry=entry, session=sess)
        ctx = context_tags(
            strategy=signal.strategy,
            side=side,
            reason=signal.reason,
            ts=signal.timestamp,
            session=sess,
        )
        return self._advise(feats, ctx)

    def advise_from_parts(
        self,
        *,
        strategy: str | None,
        side: str,
        reason: str | None,
        ts: datetime | None,
        entry: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        session: str | None = None,
    ) -> Advice:
        sess = session or session_bucket(ts)
        feats = vectorize(
            strategy=strategy,
            side=side,
            reason=reason,
            ts=ts,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            session=sess,
        )
        ctx = context_tags(
            strategy=strategy,
            side=side,
            reason=reason,
            ts=ts,
            session=sess,
        )
        return self._advise(feats, ctx)

    def _smc_sell_overlap_block_reason(self, ctx: dict[str, Any]) -> str | None:
        """Safety rail for toxic SMC SELL in London/NY overlap.

        BUY is never blocked here. SELL is allowed on cold-start so the desk can
        trade; only after enough *labeled* samples with a weak win rate do we SKIP.
        (Blocking cold-start permanently froze overlap — n could never reach min_n.)
        """
        if not self.block_smc_sell_overlap:
            return None
        if (ctx.get("strategy") or "") != "smc":
            return None
        if (ctx.get("side") or "").upper() != "SELL":
            return None
        if (ctx.get("session") or "") != "overlap":
            return None
        bucket = self.store.bucket_stats(strategy="smc", side="SELL", session="overlap")
        n = int(bucket.get("n") or 0)
        wr = bucket.get("win_rate")
        min_n = max(1, int(self.smc_sell_overlap_min_n))
        min_wr = float(self.smc_sell_overlap_min_wr)
        # Cold-start: allow SELL so frequency is not stuck at zero forever.
        if n < min_n:
            return None
        if wr is not None and wr < min_wr:
            return (
                f"Safety: SMC SELL overlap blocked "
                f"(WR {wr:.0%} < {min_wr:.0%} on {n} samples)"
            )
        return None

    def _advise(self, feats: dict[str, float], ctx: dict[str, Any]) -> Advice:
        """Score with ML probability, plus hard safety rails for known toxic setups."""
        p = float(self.model.predict_proba(feats))
        drivers = self.model.top_drivers(feats)
        samples = self.model.samples_seen
        # Confidence from sample size + distance from 0.5 decision boundary
        margin = abs(p - 0.5) * 2.0
        conf = min(0.35 + 0.015 * samples + 0.35 * margin, 0.95) if samples else (
            0.40 + 0.35 * margin
        )

        reasons: list[str] = [
            f"ML win probability {p:.0%} ({self.model.backend})"
        ]
        metrics = self.model.last_metrics or {}
        if metrics.get("accuracy") is not None:
            reasons.append(
                f"Model accuracy {metrics['accuracy']:.0%} on {metrics.get('samples', samples)} samples"
            )

        for d in drivers[:3]:
            name = str(d["feature"]).replace("_", " ")
            if d["helps"]:
                reasons.append(f"ML feature + {name}")
            else:
                reasons.append(f"ML feature − {name}")

        stats = self.store.stats()
        if stats.get("labeled"):
            reasons.append(
                f"Training history {stats['labeled']} labeled · "
                f"WR {stats.get('win_rate_pct')}%"
            )

        if p >= 0.55:
            action = "TAKE"
        elif p >= self.min_win_prob:
            action = "CAUTION"
        else:
            action = "SKIP"

        safety = self._smc_sell_overlap_block_reason(ctx)
        if safety:
            action = "SKIP"
            reasons.insert(0, safety)
            # Raise confidence so gate_entries reliably blocks the fill path too.
            conf = max(conf, self.skip_confidence)

        gated = bool(
            self.enabled
            and self.gate_entries
            and action == "SKIP"
            and conf >= self.skip_confidence
        )
        return Advice(
            action=action,
            win_probability=round(p, 3),
            confidence=round(conf, 3),
            reasons=reasons[:6],
            drivers=drivers,
            context=ctx,
            model_samples=samples,
            gated=gated,
            source="AI & Machine Learning",
        )

    def should_block(self, advice: Advice) -> bool:
        return bool(self.enabled and self.gate_entries and advice.gated)

    def record_open_from_trade(
        self,
        trade: TradeLog,
        *,
        account_id: str | None = None,
        mode: str = "paper",
        session: str | None = None,
    ) -> dict[str, Any]:
        sess = session or session_bucket(trade.opened_at)
        feats = features_from_trade(trade, session=sess)
        side = trade.side.value if hasattr(trade.side, "value") else str(trade.side)
        ctx = context_tags(
            strategy=trade.strategy,
            side=side,
            reason=trade.comment,
            ts=trade.opened_at,
            session=sess,
        )
        return self.store.record_open(
            ticket=str(trade.ticket or trade.id),
            account_id=account_id,
            features=feats,
            context=ctx,
            entry=trade.entry,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            mode=mode,
        )

    def record_close_from_trade(self, trade: TradeLog) -> dict[str, Any] | None:
        labeled = self.store.record_close(
            ticket=str(trade.ticket or trade.id),
            realized_pnl=trade.realized_pnl,
            close_reason=trade.close_reason,
            exit_price=trade.exit,
        )
        if labeled and labeled.get("label") is not None and labeled.get("features"):
            self.model.partial_fit(labeled["features"], int(labeled["label"]))
        return labeled

    def ingest_closed_trades(
        self, trades: list[TradeLog], *, account_id: str | None = None
    ) -> int:
        existing = {r.get("ticket") for r in self.store.labeled()}
        existing.update(
            r.get("ticket")
            for r in self.store.recent(500)
            if r.get("event") in {"open", "labeled"}
        )
        n = 0
        for trade in trades:
            status = (
                trade.status.value if hasattr(trade.status, "value") else str(trade.status)
            )
            if status != "CLOSED":
                continue
            ticket = str(trade.ticket or trade.id)
            if ticket in existing:
                continue
            self.record_open_from_trade(
                trade, account_id=account_id, mode=trade.mode or "paper"
            )
            self.record_close_from_trade(trade)
            existing.add(ticket)
            n += 1
        return n

    def status(self) -> dict[str, Any]:
        return {
            "name": "AI & Machine Learning",
            "enabled": self.enabled,
            "gate_entries": self.gate_entries,
            "min_win_prob": self.min_win_prob,
            "skip_confidence": self.skip_confidence,
            "block_smc_sell_overlap": self.block_smc_sell_overlap,
            "smc_sell_overlap_min_wr": self.smc_sell_overlap_min_wr,
            "smc_sell_overlap_min_n": self.smc_sell_overlap_min_n,
            "history": self.store.stats(),
            "model": self.model.snapshot(),
        }

    def retrain(self) -> dict[str, Any]:
        n = self.model.fit_many(self.store.labeled(), epochs=5)
        return {
            "name": "AI & Machine Learning",
            "retrained_on": n,
            "model": self.model.snapshot(),
        }
