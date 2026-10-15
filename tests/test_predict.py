"""Tests for scripts.predict (make predict): evaluation, gate and what gets written to Neo4j."""
# pylint: disable=missing-function-docstring

import json

import pytest
from neo4j.exceptions import ServiceUnavailable

from scripts import common, predict
from scripts import link_prediction as lp
from tests.fakes import FakeDriver


def synthetic_cves():
    """60 mapped CVEs where the CWE decides the technique, plus 6 unmapped ones."""
    cves = []
    for i in range(60):
        web = i % 2 == 0
        cves.append(lp.Cve(cve_id=f"CVE-2024-{i:04d}", date_added=f"2024-{1 + i // 6:02d}-{1 + i % 6:02d}",
                           name=f"bug {i}", cwes=frozenset({"CWE-79" if web else "CWE-787"}),
                           products=frozenset({f"v{i % 3}:p"}), vendors=frozenset({f"v{i % 3}"}),
                           techniques=frozenset({"T1190" if web else "T1203", "T1059"} if i % 5 == 0
                                                else {"T1190" if web else "T1203"}),
                           cvss_score=9.0))
    for i in range(6):
        cves.append(lp.Cve(cve_id=f"CVE-2025-{i:04d}", date_added="2025-06-01",
                           cwes=frozenset({"CWE-79" if i % 2 == 0 else "CWE-787"})))
    return cves


@pytest.fixture(name="report", scope="module")
def fixture_report():
    return predict.evaluation(synthetic_cves(), {"T1190": "Exploit Public-Facing Application"})


def test_evaluation_reports_every_model_on_validation_and_test(report):
    assert set(report["models"]) == {"random_forest", "logistic_regression", "popularity_baseline"}
    for splits in report["models"].values():
        assert set(splits) == {"validation", "test"}
        assert {"aucpr", "precision_at_3", "recall_at_3"} <= set(splits["test"])
    assert report["split"]["train"]["to"] < report["split"]["validation"]["from"]
    assert report["split"]["validation"]["to"] < report["split"]["test"]["from"]


def test_evaluation_reports_importances_and_a_hand_check_sample(report):
    assert {item["feature"] for item in report["feature_importance"]} == set(lp.FEATURES)
    assert report["feature_importance"][0]["feature"] == "cwe_vote"
    sample = report["hand_check"]
    assert sample and len(sample) <= predict.HAND_CHECK_SIZE
    assert {"cve_id", "name", "suggested", "probability", "matches_ctid", "ctid"} <= set(sample[0])


def test_gate_passes_only_with_a_clear_margin():
    def report_with(model_p3, model_aucpr, base_p3=0.30, base_aucpr=0.20):
        return {"models": {"random_forest": {"test": {"precision_at_3": model_p3, "aucpr": model_aucpr}},
                           "popularity_baseline": {"test": {"precision_at_3": base_p3, "aucpr": base_aucpr}}}}

    assert predict.passes_gate(report_with(0.36, 0.25))
    assert not predict.passes_gate(report_with(0.34, 0.25))   # precision gain below the margin
    assert not predict.passes_gate(report_with(0.40, 0.19))   # AUCPR not better


def test_final_suggestions_carry_provenance_and_explanations():
    rows = predict.final_suggestions(synthetic_cves(), threshold=0.0)
    assert rows and {r["cve_id"] for r in rows} <= {f"CVE-2025-{i:04d}" for i in range(6)}
    assert all(len([r for r in rows if r["cve_id"] == c]) <= predict.SUGGESTIONS_PER_CVE
               for c in {r["cve_id"] for r in rows})
    first = rows[0]
    assert first["model"] == "random_forest" and first["model_version"].startswith("rf-")
    assert 0 <= first["confidence"] <= 1 and first["rationale"]
    assert all("=" in feature for feature in first["top_features"])


def test_model_version_is_stable():
    cves = synthetic_cves()
    assert predict.model_version(cves, 0.5) == predict.model_version(cves, 0.5)
    assert predict.model_version(cves, 0.5) != predict.model_version(cves, 0.6)


GATED = {"split": {}, "models": {"random_forest": {}}, "threshold": None, "feature_importance": [],
         "hand_check": []}


def install(monkeypatch, tmp_path, report, driver=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    driver = driver or FakeDriver(lambda query, parameters: [])
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)
    monkeypatch.setattr(predict, "load_cves", lambda _driver: (synthetic_cves(), {}))
    monkeypatch.setattr(predict, "evaluation", lambda cves, names: report)
    monkeypatch.setattr(predict, "log_report", lambda report: None)
    return driver


def written(driver, query):
    return [params for q, params, _ in driver.queries if q == query]


def test_gated_run_stores_nothing_but_records_why(monkeypatch, tmp_path):
    driver = install(monkeypatch, tmp_path, GATED)
    assert predict.main([]) == 0
    assert [q for q, _, _ in driver.queries][0] == predict.DELETE_QUERY
    assert not written(driver, predict.STORE_QUERY)
    meta = written(driver, predict.IMPORT_META_QUERY)[0]
    assert meta["status"].startswith("not stored") and meta["suggestions"] == 0
    assert json.loads((tmp_path / "processed" / "link_prediction_report.json").read_text()) == GATED


def test_threshold_but_failed_gate_still_stores_nothing(monkeypatch, tmp_path):
    report = GATED | {"threshold": {"threshold": 0.5}}
    monkeypatch.setattr(predict, "passes_gate", lambda report: False)
    driver = install(monkeypatch, tmp_path, report)
    assert predict.main([]) == 0
    assert written(driver, predict.IMPORT_META_QUERY)[0]["status"] == predict.NOT_STORED
    assert not written(driver, predict.STORE_QUERY)


def test_passing_gate_stores_suggestions(monkeypatch, tmp_path):
    monkeypatch.setattr(predict, "passes_gate", lambda report: True)
    driver = install(monkeypatch, tmp_path, GATED | {"threshold": {"threshold": 0.0}})
    assert predict.main([]) == 0
    stored = written(driver, predict.STORE_QUERY)[0]["rows"]
    assert stored and all(row["model"] == "random_forest" for row in stored)
    meta = written(driver, predict.IMPORT_META_QUERY)[0]
    assert meta["status"] == "stored" and meta["suggestions"] == len(stored)


def test_force_stores_despite_the_gate_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(predict, "passes_gate", lambda report: False)
    driver = install(monkeypatch, tmp_path, GATED | {"threshold": {"threshold": 0.0}})
    assert predict.main(["--force"]) == 0
    assert written(driver, predict.IMPORT_META_QUERY)[0]["status"].startswith("stored with --force")


def test_evaluate_only_changes_nothing_in_neo4j(monkeypatch, tmp_path):
    driver = install(monkeypatch, tmp_path, GATED)
    assert predict.main(["--evaluate-only"]) == 0
    assert not driver.queries


def test_main_fails_without_data_or_database(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, GATED)
    monkeypatch.setattr(predict, "load_cves", lambda _driver: ([], {}))
    assert predict.main([]) == 1

    def down(query, parameters):
        raise ServiceUnavailable("down")

    install(monkeypatch, tmp_path, GATED, FakeDriver(down))
    monkeypatch.setattr(predict, "load_cves", lambda driver: driver.execute_query("RETURN 1"))
    assert predict.main([]) == 1


def test_load_cves_maps_records():
    record = {"cve_id": "CVE-1", "date_added": "2024-01-01", "name": "n", "cvss_score": 9.8,
              "ssvc_exploitation": "active", "ssvc_automatable": "no", "ssvc_technical_impact": "total",
              "ransomware": True, "cwes": ["CWE-79"], "products": ["a:b"], "vendors": ["a"], "techniques": ["T1"]}

    def responder(query, _parameters):
        return [record] if query == predict.LOAD_QUERY else [{"attack_id": "T1", "name": "One"}]

    cves, names = predict.load_cves(FakeDriver(responder))
    assert cves[0].cwes == frozenset({"CWE-79"}) and cves[0].known_ransomware_use and names == {"T1": "One"}
