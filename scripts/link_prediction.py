"""Link prediction CVE -> Technique (D18): split, features, models, metrics, threshold and explanations.

No database access here; scripts.predict loads the data from Neo4j and stores the results.

Leakage safeguards:
- the split is by CVE and by date (KEV dateAdded), so a test CVE has none of its techniques visible,
  just like the unmapped CVEs we want to predict for;
- every graph feature is computed from a *reference* set of CVEs whose technique edges are visible
  (the training CVEs during evaluation), and a CVE never counts itself (leave-one-out).
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "technique_prior",      # share of reference CVEs mapped to the technique (popularity)
    "cwe_vote",             # share of reference CVEs sharing a CWE with this CVE that map to the technique
    "cwe_neighbours",       # how many reference CVEs share a CWE with this CVE
    "product_vote",
    "product_neighbours",
    "vendor_vote",
    "vendor_neighbours",
    "cvss_score",
    "ssvc_exploitation_active",
    "ssvc_automatable",
    "ssvc_impact_total",
    "known_ransomware_use",
]
NEIGHBOUR_KINDS = ("cwe", "product", "vendor")

RANDOM_FOREST_PARAMS = {"n_estimators": 300, "min_samples_leaf": 5, "class_weight": "balanced_subsample",
                        "random_state": 42, "n_jobs": -1}
LOGISTIC_REGRESSION_PARAMS = {"max_iter": 2000, "class_weight": "balanced"}


@dataclass(frozen=True)
class Cve:  # pylint: disable=too-many-instance-attributes  # plain record: one field per model input
    """What the model may know about a CVE. `techniques` are its verified CTID mappings (empty if unmapped)."""

    cve_id: str
    date_added: str
    name: str = ""
    cwes: frozenset[str] = frozenset()
    products: frozenset[str] = frozenset()
    vendors: frozenset[str] = frozenset()
    techniques: frozenset[str] = frozenset()
    cvss_score: float | None = None
    ssvc_exploitation: str | None = None
    ssvc_automatable: str | None = None
    ssvc_technical_impact: str | None = None
    known_ransomware_use: bool = False

    def linked(self, kind: str) -> frozenset[str]:
        """The CVE's CWEs, products or vendors."""
        return {"cwe": self.cwes, "product": self.products, "vendor": self.vendors}[kind]


def temporal_split(cves: Iterable[Cve], train: float = 0.6,
                   validation: float = 0.2) -> tuple[list[Cve], list[Cve], list[Cve]]:
    """Split the mapped CVEs by KEV date: oldest for training, then validation, newest for testing.

    Cuts fall on whole dates, so CVEs added on the same day always end up in the same split.
    """
    mapped = sorted((c for c in cves if c.techniques), key=lambda c: (c.date_added, c.cve_id))
    if not mapped:
        return [], [], []
    first_cut = mapped[min(int(len(mapped) * train), len(mapped) - 1)].date_added
    second_cut = mapped[min(int(len(mapped) * (train + validation)), len(mapped) - 1)].date_added
    return ([c for c in mapped if c.date_added < first_cut],
            [c for c in mapped if first_cut <= c.date_added < second_cut],
            [c for c in mapped if c.date_added >= second_cut])


@dataclass
class Reference:
    """The CVEs whose technique edges the features may use, indexed for neighbour lookups."""

    cves: list[Cve]
    by_id: dict[str, Cve] = field(init=False)
    index: dict[str, dict[str, set[str]]] = field(init=False)
    technique_counts: Counter = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {c.cve_id: c for c in self.cves}
        self.index = {kind: {} for kind in NEIGHBOUR_KINDS}
        for cve in self.cves:
            for kind in NEIGHBOUR_KINDS:
                for key in cve.linked(kind):
                    self.index[kind].setdefault(key, set()).add(cve.cve_id)
        self.technique_counts = Counter(t for c in self.cves for t in c.techniques)

    @property
    def techniques(self) -> list[str]:
        """Candidate techniques: every technique at least one reference CVE maps to."""
        return sorted(self.technique_counts)

    def neighbours(self, cve: Cve, kind: str) -> set[str]:
        """Reference CVEs sharing at least one CWE/product/vendor with cve, never cve itself."""
        found: set[str] = set()
        for key in cve.linked(kind):
            found |= self.index[kind].get(key, set())
        found.discard(cve.cve_id)
        return found

    def prior(self, cve: Cve, technique: str) -> float:
        """Share of reference CVEs mapped to technique, leaving cve out if it is a reference CVE."""
        count, total = self.technique_counts[technique], len(self.cves)
        if cve.cve_id in self.by_id:
            count -= technique in cve.techniques
            total -= 1
        return count / total if total else 0.0


@dataclass
class Rows:
    """Feature matrix for (CVE, candidate technique) pairs, with labels and readable evidence."""

    keys: list[tuple[str, str]]
    x: np.ndarray
    y: np.ndarray
    evidence: list[dict[str, tuple[int, int]]]


def _cve_features(cve: Cve) -> list[float]:
    """The CVE's own properties, the same for every candidate technique."""
    return [cve.cvss_score or 0.0, float(cve.ssvc_exploitation == "active"), float(cve.ssvc_automatable == "yes"),
            float(cve.ssvc_technical_impact == "total"), float(cve.known_ransomware_use)]


def _neighbour_votes(cve: Cve, reference: Reference) -> dict[str, tuple[int, Counter]]:
    """For each kind, how many reference CVEs share it with cve, and how often each technique appears among them."""
    votes = {}
    for kind in NEIGHBOUR_KINDS:
        near = reference.neighbours(cve, kind)
        votes[kind] = (len(near), Counter(t for n in near for t in reference.by_id[n].techniques))
    return votes


def build_rows(cves: Iterable[Cve], reference: Reference) -> Rows:
    """One row per (CVE, candidate technique). The label is 1 if the CVE is verified-mapped to it."""
    keys, features, labels, evidence = [], [], [], []
    for cve in cves:
        own, votes = _cve_features(cve), _neighbour_votes(cve, reference)
        for technique in reference.techniques:
            row = [reference.prior(cve, technique)]
            for kind in NEIGHBOUR_KINDS:
                total, counts = votes[kind]
                row += [counts[technique] / total if total else 0.0, float(total)]
            keys.append((cve.cve_id, technique))
            features.append(row + own)
            labels.append(int(technique in cve.techniques))
            evidence.append({kind: (votes[kind][1][technique], votes[kind][0]) for kind in NEIGHBOUR_KINDS})
    return Rows(keys, np.array(features, dtype=float).reshape(-1, len(FEATURES)), np.array(labels, dtype=int),
                evidence)


def make_model(kind: str):
    """A fresh, unfitted random forest ('random_forest') or scaled logistic regression ('logistic_regression')."""
    if kind == "random_forest":
        return RandomForestClassifier(**RANDOM_FOREST_PARAMS)
    if kind == "logistic_regression":
        return make_pipeline(StandardScaler(), LogisticRegression(**LOGISTIC_REGRESSION_PARAMS))
    raise ValueError(f"unknown model {kind}")


def ranked_by_cve(keys: list[tuple[str, str]], scores: np.ndarray) -> dict[str, list[tuple[str, float]]]:
    """Each CVE's candidate techniques, highest score first (ties broken by technique id)."""
    ranked: dict[str, list[tuple[str, float]]] = {}
    for (cve_id, technique), score in zip(keys, scores):
        ranked.setdefault(cve_id, []).append((technique, float(score)))
    return {cve_id: sorted(items, key=lambda item: (-item[1], item[0])) for cve_id, items in ranked.items()}


def top_k_metrics(keys: list[tuple[str, str]], scores: np.ndarray, truth: dict[str, frozenset[str]],
                  k: int = 3) -> dict[str, float]:
    """Mean precision@k and recall@k over CVEs. Recall counts every true technique, even ones that were
    not candidates (never seen in the reference set), so it cannot be inflated by dropping them."""
    ranked = ranked_by_cve(keys, scores)
    precision, recall = [], []
    for cve_id, items in ranked.items():
        hits = sum(1 for technique, _ in items[:k] if technique in truth[cve_id])
        precision.append(hits / k)
        recall.append(hits / len(truth[cve_id]) if truth[cve_id] else 0.0)
    return {f"precision_at_{k}": float(np.mean(precision)) if precision else 0.0,
            f"recall_at_{k}": float(np.mean(recall)) if recall else 0.0}


def evaluate(rows: Rows, scores: np.ndarray, truth: dict[str, frozenset[str]], k: int = 3) -> dict[str, float]:
    """AUCPR over all candidate pairs plus precision@k and recall@k."""
    aucpr = float(average_precision_score(rows.y, scores)) if rows.y.any() else 0.0
    return {"aucpr": aucpr} | top_k_metrics(rows.keys, scores, truth, k)


def popularity_scores(rows: Rows) -> np.ndarray:
    """The baseline: score every pair by the technique's popularity, so every CVE gets the same top 3."""
    return rows.x[:, FEATURES.index("technique_prior")]


def choose_threshold(keys: list[tuple[str, str]], scores: np.ndarray, truth: dict[str, frozenset[str]], *,
                     target_precision: float = 0.7, k: int = 3, min_kept: int = 10) -> dict[str, float] | None:
    """Lowest score threshold at which the kept suggestions (top k per CVE, score >= threshold) reach the
    target precision, with at least min_kept suggestions so a handful of lucky hits cannot decide it.
    Returns None if no threshold reaches the target."""
    kept = sorted(((score, technique in truth[cve_id])
                   for cve_id, items in ranked_by_cve(keys, scores).items()
                   for technique, score in items[:k]), reverse=True)
    best, hits = None, 0
    for count, (score, hit) in enumerate(kept, start=1):
        hits += hit
        is_last_of_score = count == len(kept) or kept[count][0] != score
        if is_last_of_score and count >= min_kept and hits / count >= target_precision:
            best = {"threshold": score, "precision": hits / count, "kept": count}
    return best


def select_suggestions(keys: list[tuple[str, str]], scores: np.ndarray, threshold: float,
                       k: int = 3) -> list[tuple[str, str, float]]:
    """Top k techniques per CVE whose score reaches the threshold."""
    return [(cve_id, technique, score)
            for cve_id, items in ranked_by_cve(keys, scores).items()
            for technique, score in items[:k] if score >= threshold]


def top_features(model, row: np.ndarray, means: np.ndarray, n: int = 3) -> list[str]:
    """The features that raise this pair's score the most: each is reset to its training mean in turn and
    the drop in probability is measured (occlusion). Returned as 'name=value' strings, largest drop first."""
    base = model.predict_proba(row.reshape(1, -1))[0, 1]
    variants = np.repeat(row.reshape(1, -1), len(FEATURES), axis=0)
    variants[np.arange(len(FEATURES)), np.arange(len(FEATURES))] = means
    drops = base - model.predict_proba(variants)[:, 1]
    order = [i for i in np.argsort(-drops) if drops[i] > 0][:n]
    return [f"{FEATURES[i]}={row[i]:.2f}" for i in order]


def rationale(technique: str, evidence: dict[str, tuple[int, int]]) -> str:
    """Plain-language reason from the strongest neighbour vote, e.g. '5 of 8 mapped CVEs sharing a product
    map to T1190'."""
    kind, (hits, total) = max(evidence.items(), key=lambda item: (item[1][0] / item[1][1] if item[1][1] else 0,
                                                                   item[1][1]))
    if not total or not hits:
        return f"{technique} is common among mapped CVEs; no CVE sharing a CWE, product or vendor maps to it"
    return f"{hits} of {total} mapped CVEs sharing a {kind} map to {technique}"
