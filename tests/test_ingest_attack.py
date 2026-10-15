"""Tests for scripts.ingest_attack, on a small hand-built STIX bundle."""
# pylint: disable=missing-function-docstring

import json

import pytest
from neo4j.exceptions import ServiceUnavailable

from scripts import common, ingest_attack
from scripts.download import ATTACK, ATTACK_VERSION
from tests.fakes import FakeDriver

T0 = "2020-01-01T00:00:00.000Z"


def stix(obj_type, stix_id, attack_id=None, **extra):
    obj = {"type": obj_type, "id": stix_id, "created": T0, "modified": T0, "name": stix_id}
    if attack_id:
        obj["external_references"] = [
            {"source_name": "mitre-attack", "external_id": attack_id, "url": f"https://attack.mitre.org/{attack_id}"}
        ]
    obj.update(extra)
    return obj


def relationship(rel_id, rel_type, source, target, **extra):
    return {"type": "relationship", "id": rel_id, "relationship_type": rel_type,
            "source_ref": source, "target_ref": target, **extra}


def bundle():
    phases = [{"kill_chain_name": "mitre-attack", "phase_name": "execution"},
              {"kill_chain_name": "mitre-attack", "phase_name": "persistence"}]
    objects = [
        {"type": "x-mitre-collection", "id": "x-mitre-collection--1", "x_mitre_version": ATTACK_VERSION},
        {"type": "x-mitre-matrix", "id": "x-mitre-matrix--1",
         "tactic_refs": ["x-mitre-tactic--persist", "x-mitre-tactic--exec"]},
        stix("x-mitre-tactic", "x-mitre-tactic--exec", "TA0002", x_mitre_shortname="execution"),
        stix("x-mitre-tactic", "x-mitre-tactic--persist", "TA0003", x_mitre_shortname="persistence"),
        stix("intrusion-set", "intrusion-set--apt", "G0001", aliases=["APT", "Fancy"]),
        stix("intrusion-set", "intrusion-set--old", "G0002", x_mitre_deprecated=True),
        stix("campaign", "campaign--op", "C0001", aliases=["Op"], first_seen="2021-01-01T00:00:00.000Z",
             last_seen="2021-06-01T00:00:00.000Z"),
        stix("malware", "malware--rat", "S0001", x_mitre_aliases=["RAT"], x_mitre_platforms=["Windows"]),
        stix("tool", "tool--psexec", "S0002", x_mitre_platforms=["Windows"]),
        stix("attack-pattern", "attack-pattern--cmd", "T1059", kill_chain_phases=phases[:1],
             x_mitre_platforms=["Windows"]),
        stix("attack-pattern", "attack-pattern--ps", "T1059.001", kill_chain_phases=phases,
             x_mitre_is_subtechnique=True),
        stix("attack-pattern", "attack-pattern--gone", "T9999", revoked=True),
        stix("course-of-action", "course-of-action--m", "M1038"),
        {"type": "x-mitre-detection-strategy", "id": "x-mitre-detection-strategy--d"},
        relationship("relationship--1", "uses", "intrusion-set--apt", "attack-pattern--cmd", description="APT runs cmd",
                     external_references=[{"source_name": "Report", "url": "https://r.test"},
                                          {"source_name": "Book"}]),
        relationship("relationship--2", "uses", "intrusion-set--apt", "malware--rat"),
        relationship("relationship--3", "uses", "campaign--op", "attack-pattern--ps"),
        relationship("relationship--4", "uses", "campaign--op", "tool--psexec"),
        relationship("relationship--5", "uses", "malware--rat", "attack-pattern--cmd"),
        relationship("relationship--6", "mitigates", "course-of-action--m", "attack-pattern--cmd"),
        relationship("relationship--7", "attributed-to", "campaign--op", "intrusion-set--apt"),
        relationship("relationship--8", "subtechnique-of", "attack-pattern--ps", "attack-pattern--cmd"),
        relationship("relationship--9", "uses", "intrusion-set--apt", "attack-pattern--gone"),
        relationship("relationship--10", "detects", "x-mitre-detection-strategy--d", "attack-pattern--cmd"),
        relationship("relationship--11", "revoked-by", "attack-pattern--gone", "attack-pattern--cmd"),
        relationship("relationship--12", "uses", "intrusion-set--apt", "tool--psexec", revoked=True),
    ]
    return {"type": "bundle", "objects": objects}


@pytest.fixture(name="data")
def fixture_data():
    return ingest_attack.parse_bundle(bundle())


def test_parse_keeps_only_live_objects(data):
    assert {kind: len(rows) for kind, rows in data.nodes.items()} == {
        "Tactic": 2, "Group": 1, "Campaign": 1, "Malware": 1, "Tool": 1, "Technique": 2, "Mitigation": 1}
    assert data.skipped["intrusion-set: revoked or deprecated"] == 1
    assert data.skipped["attack-pattern: revoked or deprecated"] == 1


def test_node_rows_carry_schema_properties(data):
    group = data.nodes["Group"][0]
    assert group["props"] == {"stix_id": "intrusion-set--apt", "attack_id": "G0001", "name": "intrusion-set--apt",
                              "description": "", "url": "https://attack.mitre.org/G0001", "aliases": ["APT", "Fancy"]}
    assert group["created"] == T0
    campaign = data.nodes["Campaign"][0]
    assert campaign["first_seen"] == "2021-01-01T00:00:00.000Z"
    malware = data.nodes["Malware"][0]["props"]
    assert malware["aliases"] == ["RAT"] and malware["platforms"] == ["Windows"]
    techniques = {row["props"]["attack_id"]: row["props"] for row in data.nodes["Technique"]}
    assert techniques["T1059.001"]["is_subtechnique"] and not techniques["T1059"]["is_subtechnique"]


def test_tactic_order_follows_the_matrix(data):
    order = {row["props"]["shortname"]: row["props"]["order"] for row in data.nodes["Tactic"]}
    assert order == {"persistence": 1, "execution": 2}


def test_relationships_are_grouped_by_schema_pair(data):
    counts = {key: len(rows) for key, rows in data.relationships.items()}
    assert counts == {
        ("uses", "Group", "Technique"): 1,
        ("uses", "Group", "Software"): 1,
        ("uses", "Campaign", "Technique"): 1,
        ("uses", "Campaign", "Software"): 1,
        ("uses", "Software", "Technique"): 1,
        ("mitigates", "Mitigation", "Technique"): 1,
        ("attributed-to", "Campaign", "Group"): 1,
        ("subtechnique-of", "Technique", "Technique"): 1,
        ("in-tactic", "Technique", "Tactic"): 3,
    }


def test_relationship_rows_carry_provenance_and_citations(data):
    row = data.relationships[("uses", "Group", "Technique")][0]
    assert row["props"] == {"source": "attack", "stix_id": "relationship--1", "description": "APT runs cmd",
                            "references": ["Report (https://r.test)", "Book"]}


def test_skipped_relationships_are_counted_with_reasons(data):
    assert data.skipped["uses: revoked or deprecated end"] == 2
    assert data.skipped["detects (x-mitre-detection-strategy -> attack-pattern)"] == 1
    assert data.skipped["revoked-by (attack-pattern -> attack-pattern)"] == 1


def test_expected_counts(data):
    counts = data.expected_counts()
    assert counts["Technique"] == 2 and counts["SubTechnique"] == 1
    assert counts["USES"] == 5 and counts["IN_TACTIC"] == 3


def test_attack_reference_requires_an_id():
    with pytest.raises(ValueError, match="no ATT&CK id"):
        ingest_attack.attack_reference({"id": "x--1", "external_references": []})


def test_unknown_kill_chain_phase_is_skipped():
    objects = bundle()["objects"]
    objects.append(stix("attack-pattern", "attack-pattern--odd", "T0001",
                        kill_chain_phases=[{"kill_chain_name": "mitre-attack", "phase_name": "unknown"}]))
    data = ingest_attack.parse_bundle({"type": "bundle", "objects": objects})
    assert data.skipped["kill chain phase without tactic: unknown"] == 1


def test_load_writes_nodes_before_relationships(data):
    driver = FakeDriver()
    ingest_attack.load(driver, data, batch_size=10)
    queries = [q for q, _, _ in driver.queries]
    first_rel = next(i for i, q in enumerate(queries) if "MATCH (s:" in q)
    assert all("MERGE (n:" in q for q in queries[:first_rel - 1])
    assert queries[first_rel - 1] == ingest_attack.MARK_SUBTECHNIQUES
    assert all("MERGE (s)-[r:" in q for q in queries[first_rel:])


def test_every_query_is_parameterized(data):
    driver = FakeDriver()
    ingest_attack.load(driver, data)
    for query, params, _ in driver.queries:
        assert "intrusion-set--apt" not in query
        if params is not None:
            assert set(params) == {"rows"}


def write_raw(tmp_path, with_manifest=True):
    raw = tmp_path / "raw"
    (raw / ATTACK.name).mkdir(parents=True)
    (raw / ATTACK.name / ATTACK.filename).write_text(json.dumps(bundle()), encoding="utf-8")
    if with_manifest:
        (raw / "manifest.json").write_text(json.dumps({"attack": {"version": ATTACK_VERSION, "sha256": "abc"}}),
                                           encoding="utf-8")


def install(monkeypatch, tmp_path, driver):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)


def counting_driver(expected):
    def responder(query, _parameters):
        return [expected] if query.startswith("RETURN COUNT") else []

    return FakeDriver(responder)


def test_main_loads_records_import_and_verifies(monkeypatch, tmp_path):
    write_raw(tmp_path)
    driver = counting_driver(ingest_attack.parse_bundle(bundle()).expected_counts())
    install(monkeypatch, tmp_path, driver)
    assert ingest_attack.main() == 0
    meta = next(params for query, params, _ in driver.queries if query.startswith("MERGE (m:ImportMeta"))
    assert meta == {"source": "attack", "version": ATTACK_VERSION, "file": ATTACK.filename, "sha256": "abc"}


def test_main_reports_count_mismatch(monkeypatch, tmp_path):
    write_raw(tmp_path, with_manifest=False)
    counts = ingest_attack.parse_bundle(bundle()).expected_counts() | {"USES": 0}
    install(monkeypatch, tmp_path, counting_driver(counts))
    assert ingest_attack.main() == 1


def test_main_requires_download(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_attack.main() == 1


def test_main_rejects_wrong_version(monkeypatch, tmp_path):
    write_raw(tmp_path)
    path = tmp_path / "raw" / ATTACK.name / ATTACK.filename
    path.write_text(json.dumps({"type": "bundle", "objects": []}), encoding="utf-8")
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_attack.main() == 1


def test_main_fails_when_neo4j_is_down(monkeypatch, tmp_path):
    write_raw(tmp_path)

    def responder(query, parameters):
        raise ServiceUnavailable("down")

    install(monkeypatch, tmp_path, FakeDriver(responder))
    assert ingest_attack.main() == 1
