"""AI & Machine Learning models for win-probability scoring.

Primary stack (scikit-learn):
- ``SGDClassifier(log_loss)`` — online learning on each closed trade
- ``LogisticRegression`` — batch retrain on full labeled history

Falls back to pure-Python logistic regression if sklearn is unavailable.
Feature vectors always include a constant ``bias=1.0`` column; models use
``fit_intercept=False`` so the bias weight is learned explicitly.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

from app.ai.features import FEATURE_KEYS

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression, SGDClassifier
    from sklearn.metrics import accuracy_score, log_loss

    HAS_SKLEARN = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    LogisticRegression = None  # type: ignore
    SGDClassifier = None  # type: ignore
    accuracy_score = None  # type: ignore
    log_loss = None  # type: ignore
    HAS_SKLEARN = False


def _sigmoid(x: float) -> float:
    if x >= 20:
        return 1.0
    if x <= -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _default_weights() -> dict[str, float]:
    """Cold-start ML coefficients (mild — keep Asia/overlap tradeable).

    Strong negative Asia/soft priors previously pushed almost every AI_ML child
    under the 0.40 CAUTION floor → zero fills after the Aug 12 safety deploy.
    """
    weights = {k: 0.0 for k in FEATURE_KEYS}
    weights["bias"] = 0.10
    weights["soft_confirm"] = -0.25  # prefer engulf/pin, but don't freeze Asia
    weights["sess_asia"] = -0.15
    weights["sess_london"] = 0.10
    weights["sess_overlap"] = 0.35
    weights["sess_ny"] = 0.20
    weights["strat_ema_rsi"] = 0.05
    weights["strat_smc"] = 0.15
    weights["strat_judas"] = 0.15
    weights["strat_vwap"] = 0.10
    return weights


class OnlineLogisticModel:
    """AI & Machine Learning win classifier."""

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
        self.weights: dict[str, float] = _default_weights()
        self.samples_seen = 0
        self.backend = "sklearn" if HAS_SKLEARN else "pure_python"
        self.last_metrics: dict[str, Any] = {}
        self._sgd = None
        if HAS_SKLEARN:
            self._init_sgd_from_weights()
        if self.path:
            self.load()

    def _init_sgd_from_weights(self) -> None:
        assert HAS_SKLEARN and np is not None
        self._sgd = SGDClassifier(
            loss="log_loss",
            penalty="l2",
            alpha=self.l2,
            fit_intercept=False,
            learning_rate="optimal",
            random_state=42,
        )
        coef = np.array([self.weights[k] for k in FEATURE_KEYS], dtype=float).reshape(1, -1)
        # Warm-start fitted state, then overwrite coefficients with priors.
        self._sgd.partial_fit(coef, np.array([1]), classes=np.array([0, 1]))
        self._sgd.coef_ = coef.copy()
        self._sgd.intercept_ = np.array([0.0], dtype=float)

    def _vector(self, features: dict[str, float]):
        assert np is not None
        return np.array([[float(features.get(k, 0.0)) for k in FEATURE_KEYS]], dtype=float)

    def _matrix(self, rows: list[dict[str, Any]]):
        assert np is not None
        return np.array(
            [[float(r["features"].get(k, 0.0)) for k in FEATURE_KEYS] for r in rows],
            dtype=float,
        )

    def _sync_weights_from_sgd(self) -> None:
        if self._sgd is None:
            return
        coef = self._sgd.coef_.ravel()
        for i, key in enumerate(FEATURE_KEYS):
            self.weights[key] = float(coef[i])

    def predict_proba(self, features: dict[str, float]) -> float:
        if HAS_SKLEARN and self._sgd is not None:
            try:
                proba = self._sgd.predict_proba(self._vector(features))[0]
                classes = list(self._sgd.classes_)
                if 1 in classes:
                    return float(proba[classes.index(1)])
                return float(proba[-1])
            except Exception:
                pass
        z = sum(
            self.weights.get(key, 0.0) * float(features.get(key, 0.0))
            for key in FEATURE_KEYS
        )
        return _sigmoid(z)

    def partial_fit(self, features: dict[str, float], label: int) -> float:
        """One online ML update. Returns probability before the update."""
        y = 1 if int(label) == 1 else 0
        with self._lock:
            p = self.predict_proba(features)
            if HAS_SKLEARN and self._sgd is not None:
                self._sgd.partial_fit(self._vector(features), np.array([y]))
                self._sync_weights_from_sgd()
            else:
                err = p - float(y)
                for key in FEATURE_KEYS:
                    x = float(features.get(key, 0.0))
                    grad = err * x + self.l2 * self.weights.get(key, 0.0)
                    self.weights[key] = self.weights.get(key, 0.0) - self.lr * grad
            self.samples_seen += 1
            self.save()
            return p

    def fit_many(self, rows: list[dict[str, Any]], epochs: int = 4) -> int:
        """Batch Machine Learning retrain on labeled history."""
        labeled = [
            r
            for r in rows
            if r.get("label") is not None and isinstance(r.get("features"), dict)
        ]
        if not labeled:
            return 0
        with self._lock:
            if HAS_SKLEARN:
                X = self._matrix(labeled)
                y = np.array([int(r["label"]) for r in labeled], dtype=int)
                if len(set(y.tolist())) < 2:
                    # Single-class batches (e.g. a few manual Asia losses) drive
                    # bias/side_buy deeply negative and SKIP every setup. Keep priors.
                    self.last_metrics = {
                        "backend": "sklearn",
                        "algorithm": "SGDClassifier",
                        "samples": int(len(labeled)),
                        "note": "skipped_single_class_batch",
                    }
                    return 0
                else:
                    clf = LogisticRegression(
                        penalty="l2",
                        C=1.0 / max(self.l2, 1e-6),
                        fit_intercept=False,
                        max_iter=500,
                        solver="lbfgs",
                    )
                    clf.fit(X, y)
                    self._sgd = SGDClassifier(
                        loss="log_loss",
                        penalty="l2",
                        alpha=self.l2,
                        fit_intercept=False,
                        learning_rate="optimal",
                        random_state=42,
                    )
                    self._sgd.partial_fit(X, y, classes=np.array([0, 1]))
                    self._sgd.coef_ = clf.coef_.copy()
                    self._sgd.intercept_ = np.zeros(1, dtype=float)
                    self._sync_weights_from_sgd()
                    pred = clf.predict(X)
                    proba = clf.predict_proba(X)
                    self.last_metrics = {
                        "backend": "sklearn",
                        "algorithm": "LogisticRegression + SGDClassifier",
                        "samples": int(len(labeled)),
                        "accuracy": round(float(accuracy_score(y, pred)), 4),
                        "log_loss": round(float(log_loss(y, proba)), 4),
                        "positive_rate": round(float(y.mean()), 4),
                    }
                self.samples_seen = max(self.samples_seen, len(labeled))
            else:
                for _ in range(max(1, epochs)):
                    for row in labeled:
                        yv = 1.0 if int(row["label"]) == 1 else 0.0
                        feats = row["features"]
                        p = self.predict_proba(feats)
                        err = p - yv
                        for key in FEATURE_KEYS:
                            x = float(feats.get(key, 0.0))
                            grad = err * x + self.l2 * self.weights.get(key, 0.0)
                            self.weights[key] = self.weights.get(key, 0.0) - self.lr * grad
                        self.samples_seen += 1
                self.last_metrics = {
                    "backend": "pure_python",
                    "algorithm": "online_logistic",
                    "samples": len(labeled),
                }
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
        return [
            {
                "feature": key,
                "contribution": round(contrib, 3),
                "helps": contrib > 0,
            }
            for _, key, contrib in scored[:limit]
        ]

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": "AI & Machine Learning",
            "backend": self.backend,
            "weights": self.weights,
            "samples_seen": self.samples_seen,
            "lr": self.lr,
            "l2": self.l2,
            "metrics": self.last_metrics,
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
        self.last_metrics = payload.get("metrics") or {}
        # Heal models poisoned by tiny all-loss batches (bias≪0 → SKIP everything).
        if self._looks_poisoned():
            self.weights = _default_weights()
            self.samples_seen = 0
            self.last_metrics = {
                "note": "reset_poisoned_weights",
                "previous_bias": float(weights.get("bias", 0.0) or 0.0),
            }
            if HAS_SKLEARN:
                self._init_sgd_from_weights()
            self.save()
            return True
        if HAS_SKLEARN:
            self._init_sgd_from_weights()
        return True

    def _looks_poisoned(self) -> bool:
        bias = float(self.weights.get("bias", 0.0))
        side_buy = float(self.weights.get("side_buy", 0.0))
        sess_asia = float(self.weights.get("sess_asia", 0.0))
        # After Aug 12, a 4-loss manual Asia batch drove these ≪ -1.0.
        return bias < -0.5 or (side_buy < -0.5 and sess_asia < -0.5)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": "AI & Machine Learning",
            "backend": "sklearn" if HAS_SKLEARN else "pure_python",
            "algorithm": (
                "LogisticRegression + SGDClassifier (log_loss)"
                if HAS_SKLEARN
                else "online_logistic"
            ),
            "samples_seen": self.samples_seen,
            "weights": {k: round(v, 4) for k, v in self.weights.items() if abs(v) > 1e-4},
            "metrics": self.last_metrics,
            "path": str(self.path) if self.path else None,
            "sklearn": HAS_SKLEARN,
        }
