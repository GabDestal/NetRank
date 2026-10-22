"""The served winner model: a logistic regression exported to JSON (no scikit-learn in the API image).

Artifact (written by scripts/train.py, read here):
  version, createdAt, kind ("logistic"), features [names], weights [w per feature, already divided by
  the training scale], trainedOn {...}, servingSnapshot {cutoff, prestige, recent, embeddings}, metrics.
P(p1 wins) = sigmoid(sum_j w_j * x_j). No intercept: features are antisymmetric, so
P(p1 beats p2) + P(p2 beats p1) = 1 exactly (decision log D51).
"""

import json
import math
import threading
from datetime import date
from pathlib import Path

from app.errors import GdsUnavailableError
from app.ml.features import FEATURES, Snapshot

_cache: dict[str, "WinnerModel"] = {}
_lock = threading.Lock()


class ModelUnavailableError(GdsUnavailableError):
    """No trained model artifact (HTTP 503)."""


class WinnerModel:
    """Logistic model plus the snapshot used for predictions 'as of now'."""

    def __init__(self, artifact: dict) -> None:
        """Validate the artifact layout and index its parts."""
        if artifact.get("kind") != "logistic" or artifact.get("features") != list(FEATURES):
            raise ModelUnavailableError("Model artifact does not match this API version: run make train")
        self.version: str = artifact["version"]
        self.weights = dict(zip(artifact["features"], artifact["weights"]))
        self.metrics: dict = artifact.get("metrics", {})
        serving = artifact["servingSnapshot"]
        self.snapshot = Snapshot(
            cutoff=date.fromisoformat(serving["cutoff"]),
            prestige={int(k): v for k, v in serving["prestige"].items()},
            recent={int(k): v for k, v in serving["recent"].items()},
            embeddings={int(k): v for k, v in serving["embeddings"].items()},
        )

    def logit(self, features: dict[str, float]) -> float:
        """Linear score; positive favours p1."""
        return sum(self.weights[name] * features[name] for name in FEATURES)

    def probability(self, features: dict[str, float]) -> float:
        """P(p1 wins)."""
        return 1.0 / (1.0 + math.exp(-self.logit(features)))

    def contributions(self, features: dict[str, float], top: int = 5) -> list[dict]:
        """Largest |w * x| terms, with the 64 FastRP terms summed into one 'fastrpEmbedding' entry."""
        terms = {name: self.weights[name] * features[name] for name in FEATURES if not name.startswith("fastrp")}
        terms["fastrpEmbedding"] = sum(self.weights[n] * features[n] for n in FEATURES if n.startswith("fastrp"))
        ranked = sorted(terms.items(), key=lambda item: abs(item[1]), reverse=True)[:top]
        return [{"feature": name, "logitContribution": round(value, 4)} for name, value in ranked]


def load_model(path: str) -> WinnerModel:
    """Load (once per path and file version) the model artifact; 503 if it is missing."""
    file = Path(path)
    if not file.exists():
        raise ModelUnavailableError("Model not trained yet: run make train")
    key = f"{file.resolve()}:{file.stat().st_mtime_ns}"
    with _lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = WinnerModel(json.loads(file.read_text(encoding="utf-8")))
        return _cache[key]
