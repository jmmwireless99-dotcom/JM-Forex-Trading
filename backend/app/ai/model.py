"""Pure-Python online logistic regression for win-probability scoring."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

from app.ai.features import FEATURE_KEYS


def _sigmoid(x: float) -> float:
    if x >= 20:
        return 1.0
    if x <= -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


class OnlineLogisticModel:
    """L2-regularized logistic regression trained one closed trade at a time."""

    def __init__(
        self,
        *,
        lr: float = 0.12,
        l2: float = 0.01,
        path: str | Path | None = None,
    ) -> None:
        self.lr = lr
        self.l2 = l2
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        # Cold-start priors from desk SL audit: Asia + soft confirm hurt win rate.
        self.weights: dict[str, float] = {k: 0.0 for k in FEATURE_KEYS}
        self.weights["bias"] = 0.05
        self.weights["soft_confirm"] = -0.85
        self.weights["sess_asia"] = -0.75
        self.weights["sess_overlap"] = 0.45
        self.weights["sess_ny"] = 0.25
        self.weights["strat_ema_rsi"] = -0.15
        self.weights["strat_smc"] = 0.2
        self.samples_seen = 0
        if self.path:
            self.load()

    def predict_proba(self, features: dict[str, float]) -> float:
        z = 0.0
        for key in FEATURE_KEYS:
            z += self.weights.get(key, 0.0) * float(features.get(key, 0.0))
        return _sigmoid(z)

    def partial_fit(self, features: dict[str, float], label: int) -> float:
        """One SGD step. Returns predicted probability before the update."""
        y = 1.0 if int(label) == 1 else 0.0
        with self._lock:
            p = self.predict_proba(features)
            err = p - y
            for key in FEATURE_KEYS:
                x = float(features.get(key, 0.0))
                grad = err * x + self.l2 * self.weights.get(key, 0.0)
                self.weights[key] = self.weights.get(key, 0.0) - self.lr * grad
            self.samples_seen += 1
            self.save()
            return p

    def fit_many(self, rows: list[dict[str, Any]], epochs: int = 4) -> int:
        labeled = [
            r
            for r in rows
            if r.get("label") is not None and isinstance(r.get("features"), dict)
        ]
        if not labeled:
            return 0
        with self._lock:
            for _ in range(max(1, epochs)):
                for row in labeled:
                    y = 1.0 if int(row["label"]) == 1 else 0.0
                    feats = row["features"]
                    p = self.predict_proba(feats)
                    err = p - y
                    for key in FEATURE_KEYS:
                        x = float(feats.get(key, 0.0))
                        grad = err * x + self.l2 * self.weights.get(key, 0.0)
                        self.weights[key] = self.weights.get(key, 0.0) - self.lr * grad
                    self.samples_seen += 1
            self.save()
        return len(labeled)

    def top_drivers(
        self, features: dict[str, float], *, limit: int = 4
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, str, float]] = []
        for key in FEATURE_KEYS:
            if key == "bias":
                continue
            x = float(features.get(key, 0.0))
            if abs(x) < 1e-9:
                continue
            contrib = self.weights.get(key, 0.0) * x
            scored.append((abs(contrib), key, contrib))
        scored.sort(reverse=True)
        out = []
        for _, key, contrib in scored[:limit]:
            out.append(
                {
                    "feature": key,
                    "contribution": round(contrib, 3),
                    "helps": contrib > 0,
                }
            )
        return out

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "weights": self.weights,
            "samples_seen": self.samples_seen,
            "lr": self.lr,
            "l2": self.l2,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> bool:
        if not self.path or not self.path.exists():
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        weights = payload.get("weights") or {}
        for key in FEATURE_KEYS:
            if key in weights:
                self.weights[key] = float(weights[key])
        self.samples_seen = int(payload.get("samples_seen") or 0)
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "samples_seen": self.samples_seen,
            "weights": {k: round(v, 4) for k, v in self.weights.items() if abs(v) > 1e-4},
            "path": str(self.path) if self.path else None,
        }
