"""Tests for scripts.ingest_ctid, on small hand-built CTID and ATT&CK data."""
# pylint: disable=missing-function-docstring

import json

import pytest
from neo4j.exceptions import ServiceUnavailable

from scripts import common, ingest_ctid
from scripts.download import ATTACK, ATTACK_VERSION, CTID, CTID_ATTACK_VERSION
from tests.fakes import FakeDriver


def technique(stix_id, attack_id, **extra):
    return {"type": "attack-pattern", "id": stix_id, **extra,
            "external_references": [{"source_name": "mitre-attack", "external_id": attack_id}]}


def revoked_by(source, target):
    return {"type": "relationship", "id": f"relationship--{source}", "relationship_type": "revoked-by",
            "source_ref": source, "target_ref": target}


BUNDLE = {"type": "bundle", "objects": [
    {"type": "x-mitre-collection", "id": "x-mitre-collection--1", "x_mitre_version": ATTACK_VERSION},
    technique("attack-pattern--live", "T1190"),
    technique("attack-pattern--new", "T1685"),
    technique("attack-pattern--old", "T1562", revoked=True),
    technique("attack-pattern--older", "T1089", revoked=True),
    technique("attack-pattern--middle", "T1600", revoked=True),
    technique("attack-pattern--dead", "T1999", x_mitre_deprecated=True),
    revoked_by("attack-pattern--old", "attack-pattern--new"),
    revoked_by("attack-pattern--older", "attack-pattern--middle"),
    revoked_by("attack-pattern--middle", "attack-pattern--new"),
]}


def mapping(cve, mapping_type, attack_id, **extra):
    return {"capability_id": cve, "mapping_type": mapping_type, "attack_object_id": attack_id,
            "comments": f"{cve} via {attack_id}", "references": [f"https://ref.test/{cve}"], **extra}


CTID_FILE = {
    "metadata": {"attack_version": CTID_ATTACK_VERSION, "mapping_framework_version": "07/28/2025"},
    "mapping_objects": [
        mapping("CVE-2024-0001", "exploitation_technique", "T1190"),
        mapping("CVE-2024-0001", "primary_impact", "T1685"),
        mapping("CVE-2024-0001", "secondary_impact", "T1562"),
        mapping("CVE-2024-0002", "secondary_impact", "T1089"),
        mapping("CVE-2024-0002", "secondary_impact", "T1685"),
        mapping("CVE-2024-0003", "secondary_impact", "T1999"),
        mapping("CVE-2024-0003", "uncategorized", "T1190"),
        mapping("CVE-2024-0004", "exploitation_technique", "T1190", comments=None, references=None),
    ],
}


@pytest.fixture(name="data")
def fixture_data():
    return ingest_ctid.parse(CTID_FILE, *ingest_ctid.technique_successors(BUNDLE))


def test_successors_follow_revoked_by_chains():
    live, successors = ingest_ctid.technique_successors(BUNDLE)
    assert live == {"T1190", "T1685"}
    assert successors == {"T1562": "T1685", "T1089": "T1685", "T1600": "T1685", "T1999": None}


def test_successor_cycle_ends_without_a_successor():
    bundle = {"objects": [technique("attack-pattern--a", "T1", revoked=True),
                          technique("attack-pattern--b", "T2", revoked=True),
                          revoked_by("attack-pattern--a", "attack-pattern--b"),
                          revoked_by("attack-pattern--b", "attack-pattern--a")]}
    assert ingest_ctid.technique_successors(bundle)[1] == {"T1": None, "T2": None}


def test_mapping_date_is_iso():
    assert ingest_ctid.mapping_date({"mapping_framework_version": "7/28/2025"}) == "2025-07-28"


def test_rows_by_relationship_type(data):
    assert {rel: [(r["cve_id"], r["attack_id"]) for r in rows] for rel, rows in data.rows.items()} == {
        "EXPLOITS_VIA": [("CVE-2024-0001", "T1190"), ("CVE-2024-0004", "T1190")],
        "PRIMARY_IMPACT": [("CVE-2024-0001", "T1685")],
        "SECONDARY_IMPACT": [("CVE-2024-0001", "T1685"), ("CVE-2024-0002", "T1685")],
    }


def test_row_properties(data):
    row = data.rows["EXPLOITS_VIA"][0]
    assert row["mapping_date"] == "2025-07-28"
    assert row["props"] == {"source": "ctid", "attack_version": CTID_ATTACK_VERSION,
                            "comments": "CVE-2024-0001 via T1190", "references": ["https://ref.test/CVE-2024-0001"]}
    assert data.rows["EXPLOITS_VIA"][1]["props"]["comments"] == ""
    assert data.rows["EXPLOITS_VIA"][1]["props"]["references"] == []


def test_remaps_are_recorded_on_the_relationship_and_in_the_log(data):
    remapped = data.rows["SECONDARY_IMPACT"]
    assert remapped[0]["props"]["remapped_from"] == "T1562"
    assert remapped[1]["props"]["remapped_from"] == "T1089"
    assert data.remap_log == [
        "CVE-2024-0001 SECONDARY_IMPACT T1562 -> T1685",
        "CVE-2024-0002 SECONDARY_IMPACT T1089 -> T1685",
        "CVE-2024-0003 SECONDARY_IMPACT T1999: dropped, no live successor in ATT&CK v20",
    ]


def test_skipped_mappings_have_reasons(data):
    assert data.skipped == {
        "duplicate mapping after remap": 1,
        "mapping to a technique with no live successor": 1,
        "mapping type not in schema: uncategorized": 1,
    }


def test_expected_counts_and_endpoints(data):
    assert data.expected_counts() == {"EXPLOITS_VIA": 2, "PRIMARY_IMPACT": 1, "SECONDARY_IMPACT": 2,
                                      "mapped_CVE": 3, "remapped": 2}
    assert data.endpoint_ids() == (["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0004"], ["T1190", "T1685"])


def test_load_uses_one_parameterized_query_per_type(data):
    driver = FakeDriver()
    ingest_ctid.load(driver, data)
    assert [q for q, _, _ in driver.queries] == list(ingest_ctid.MAPPING_QUERIES.values())
    for query, params, _ in driver.queries:
        assert "CVE-2024" not in query and set(params) == {"rows"}


def bridge_driver(counts, missing_cves=(), missing_techniques=()):
    def responder(query, _parameters):
        if query == ingest_ctid.MISSING_CVES_QUERY:
            return [{"missing": list(missing_cves)}]
        if query == ingest_ctid.MISSING_TECHNIQUES_QUERY:
            return [{"missing": list(missing_techniques)}]
        return [counts] if query.startswith("RETURN COUNT") else []

    return FakeDriver(responder)


def write_raw(tmp_path):
    raw = tmp_path / "raw"
    for source, content in ((CTID, CTID_FILE), (ATTACK, BUNDLE)):
        (raw / source.name).mkdir(parents=True)
        (raw / source.name / source.filename).write_text(json.dumps(content), encoding="utf-8")
    (raw / "manifest.json").write_text(json.dumps({"ctid": {"version": "16.1", "sha256": "c"}}), encoding="utf-8")


def install(monkeypatch, tmp_path, driver):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)


def test_main_loads_records_remap_log_and_verifies(monkeypatch, tmp_path, data):
    write_raw(tmp_path)
    driver = bridge_driver(data.expected_counts())
    install(monkeypatch, tmp_path, driver)
    assert ingest_ctid.main() == 0
    meta = next(params for query, params, _ in driver.queries if query.startswith("MERGE (m:ImportMeta"))
    assert meta == {"version": "16.1", "file": CTID.filename, "sha256": "c", "attack_version": CTID_ATTACK_VERSION,
                    "remap_log": data.remap_log}


def test_main_refuses_when_endpoints_are_missing(monkeypatch, tmp_path, data):
    write_raw(tmp_path)
    driver = bridge_driver(data.expected_counts(), missing_cves=["CVE-2024-0001"])
    install(monkeypatch, tmp_path, driver)
    assert ingest_ctid.main() == 1
    assert not any(query.startswith("UNWIND $rows") for query, _, _ in driver.queries)


def test_main_reports_count_mismatch(monkeypatch, tmp_path, data):
    write_raw(tmp_path)
    install(monkeypatch, tmp_path, bridge_driver(data.expected_counts() | {"remapped": 0}))
    assert ingest_ctid.main() == 1


def test_main_requires_downloads(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_ctid.main() == 1


def test_main_rejects_wrong_attack_version(monkeypatch, tmp_path):
    write_raw(tmp_path)
    bad = CTID_FILE | {"metadata": {"attack_version": "15.1"}}
    (tmp_path / "raw" / CTID.name / CTID.filename).write_text(json.dumps(bad), encoding="utf-8")
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_ctid.main() == 1


def test_main_fails_when_neo4j_is_down(monkeypatch, tmp_path):
    write_raw(tmp_path)

    def responder(query, parameters):
        raise ServiceUnavailable("down")

    install(monkeypatch, tmp_path, FakeDriver(responder))
    assert ingest_ctid.main() == 1
