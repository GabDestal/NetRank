"""Tests for scripts.link_prediction: split, leakage safeguards, features, metrics and threshold."""
# pylint: disable=missing-function-docstring

import numpy as np
import pytest

from scripts import link_prediction as lp


def cve(cve_id, day, techniques=(), *, cwes=(), products=(), vendors=(), **extra):
    return lp.Cve(cve_id=cve_id, date_added=f"2024-01-{day:02d}", cwes=frozenset(cwes),
                  products=frozenset(products), vendors=frozenset(vendors), techniques=frozenset(techniques), **extra)


def test_temporal_split_is_by_cve_and_keeps_dates_together():
    cves = [cve(f"C{i}", day, ["T1"]) for i, day in enumerate([1, 2, 3, 3, 3, 4, 5, 6, 7, 8])]
    cves.append(cve("UNMAPPED", 9))
    train, validation, test = lp.temporal_split(cves)
    assert [c.cve_id for c in train] == ["C0", "C1", "C2", "C3", "C4", "C5"]  # day 3 stays together
    assert [c.cve_id for c in validation] == ["C6", "C7"]
    assert [c.cve_id for c in test] == ["C8", "C9"]
    assert max(c.date_added for c in train) < min(c.date_added for c in validation)
    assert all("UNMAPPED" != c.cve_id for c in train + validation + test)


def test_temporal_split_of_nothing():
    assert lp.temporal_split([cve("U", 1)]) == ([], [], [])


def test_neighbours_and_prior_leave_the_cve_itself_out():
    a = cve("A", 1, ["T1"], cwes=["CWE-79"])
    b = cve("B", 2, ["T2"], cwes=["CWE-79"])
    reference = lp.Reference([a, b])
    assert reference.neighbours(a, "cwe") == {"B"}
    assert reference.prior(a, "T1") == 0.0  # only A maps to T1, and A is left out
    assert reference.prior(a, "T2") == 1.0
    outsider = cve("X", 3, cwes=["CWE-79"])
    assert reference.prior(outsider, "T1") == 0.5 and reference.neighbours(outsider, "cwe") == {"A", "B"}


def test_a_cves_own_techniques_never_leak_into_its_features():
    a = cve("A", 1, ["T1"], cwes=["CWE-79"], products=["p:x"], vendors=["p"])
    b = cve("B", 2, ["T2"], cwes=["CWE-79"], products=["p:x"], vendors=["p"])
    rows = lp.build_rows([a], lp.Reference([a, b]))
    features = dict(zip([t for _, t in rows.keys], rows.x))
    t1 = dict(zip(lp.FEATURES, features["T1"]))
    assert t1["technique_prior"] == 0 and t1["cwe_vote"] == 0 and t1["product_vote"] == 0 and t1["vendor_vote"] == 0
    t2 = dict(zip(lp.FEATURES, features["T2"]))
    assert t2["cwe_vote"] == 1 and t2["cwe_neighbours"] == 1


def test_build_rows_labels_and_cve_features():
    target = cve("T", 5, ["T1"], cvss_score=9.8, ssvc_exploitation="active", ssvc_automatable="yes",
                 ssvc_technical_impact="total", known_ransomware_use=True)
    rows = lp.build_rows([target], lp.Reference([cve("A", 1, ["T1", "T2"])]))
    assert rows.keys == [("T", "T1"), ("T", "T2")] and list(rows.y) == [1, 0]
    values = dict(zip(lp.FEATURES, rows.x[0]))
    assert values["cvss_score"] == 9.8 and values["ssvc_exploitation_active"] == 1
    assert values["ssvc_automatable"] == 1 and values["ssvc_impact_total"] == 1 and values["known_ransomware_use"] == 1
    assert rows.evidence[0]["cwe"] == (0, 0)


def test_top_k_metrics_count_unreachable_techniques_in_recall():
    keys = [("A", "T1"), ("A", "T2"), ("A", "T3"), ("A", "T4")]
    scores = np.array([0.9, 0.8, 0.1, 0.7])
    truth = {"A": frozenset({"T1", "T9"})}  # T9 is not even a candidate
    assert lp.top_k_metrics(keys, scores, truth, k=3) == {"precision_at_3": pytest.approx(1 / 3),
                                                         "recall_at_3": 0.5}


def test_evaluate_and_baseline():
    reference = lp.Reference([cve("A", 1, ["T1"]), cve("B", 2, ["T1"]), cve("C", 3, ["T2"])])
    rows = lp.build_rows([cve("D", 4, ["T1"])], reference)
    baseline = lp.popularity_scores(rows)
    metrics = lp.evaluate(rows, baseline, {"D": frozenset({"T1"})}, k=1)
    assert metrics["precision_at_1"] == 1.0 and metrics["aucpr"] == 1.0


def test_choose_threshold_reaches_target_precision_with_enough_suggestions():
    keys = [(f"C{i}", "T1") for i in range(20)]
    scores = np.array([0.9] * 10 + [0.4] * 10)
    truth = {f"C{i}": frozenset({"T1"} if i < 8 or i == 15 else set()) for i in range(20)}
    chosen = lp.choose_threshold(keys, scores, truth, target_precision=0.7, k=1, min_kept=5)
    assert chosen == {"threshold": 0.9, "precision": 0.8, "kept": 10}


def test_choose_threshold_returns_none_when_unreachable():
    keys = [(f"C{i}", "T1") for i in range(20)]
    truth = {f"C{i}": frozenset() for i in range(20)}
    assert lp.choose_threshold(keys, np.full(20, 0.9), truth) is None


def test_select_suggestions_keeps_top_k_above_threshold():
    keys = [("A", "T1"), ("A", "T2"), ("A", "T3"), ("B", "T1")]
    picked = lp.select_suggestions(keys, np.array([0.9, 0.8, 0.85, 0.2]), threshold=0.5, k=2)
    assert picked == [("A", "T1", 0.9), ("A", "T3", 0.85)]


def test_make_model_kinds():
    assert lp.make_model("random_forest").get_params()["random_state"] == 42
    assert "logisticregression" in lp.make_model("logistic_regression").named_steps
    with pytest.raises(ValueError):
        lp.make_model("pagerank")


class StubModel:  # pylint: disable=too-few-public-methods
    """Probability = 0.5 * cwe_vote + 0.1: only cwe_vote matters."""

    def predict_proba(self, x):
        p = 0.5 * x[:, lp.FEATURES.index("cwe_vote")] + 0.1
        return np.column_stack([1 - p, p])


def test_top_features_ranks_by_probability_drop():
    row = np.zeros(len(lp.FEATURES))
    row[lp.FEATURES.index("cwe_vote")] = 0.8
    assert lp.top_features(StubModel(), row, np.zeros(len(lp.FEATURES))) == ["cwe_vote=0.80"]


def test_rationale_uses_the_strongest_vote():
    evidence = {"cwe": (2, 10), "product": (3, 4), "vendor": (0, 0)}
    assert lp.rationale("T1190", evidence) == "3 of 4 mapped CVEs sharing a product map to T1190"
    assert "common among mapped CVEs" in lp.rationale("T1059", {"cwe": (0, 0), "product": (0, 3), "vendor": (0, 0)})
