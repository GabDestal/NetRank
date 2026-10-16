"""Tests for the agent's tools (D19): argument validation, compaction, citations and provenance sets."""
# pylint: disable=missing-function-docstring

import pytest

from app.agent import tools
from app.agent.guardrails import GuardrailError
from app.agent.tools import TOOLS, ToolFailure, call_tool, collect_ids, compact
from app.services import analytics, cves, groups, products, techniques
from tests.fakes import FakeDriver, FakeSessionDriver
from tests.test_api import CVE_RECORD, EXPOSURE_RECORD, GROUP_RECORD, PRODUCT_RECORD, TECHNIQUE_RECORD, VENDOR_RECORD


def answering(mapping):
    """A fake driver answering each known query with its records, and [] otherwise."""
    return FakeDriver(lambda query, parameters: mapping.get(query, []))


def test_every_tool_has_a_described_function_spec():
    for name, tool in TOOLS.items():
        spec = tool.spec()["function"]
        assert spec["name"] == name and len(spec["description"]) > 40
        assert spec["parameters"]["type"] == "object"
    assert "HAS_WEAKNESS" in TOOLS["run_cypher"].spec()["function"]["description"]


def test_unknown_tools_and_bad_arguments_are_tool_failures():
    with pytest.raises(ToolFailure, match="Unknown tool"):
        call_tool(FakeDriver(), "drop_database", {})
    with pytest.raises(ToolFailure, match="group_id"):
        call_tool(FakeDriver(), "group_techniques", {"group_id": "APT29"})


def test_collect_ids_and_compact():
    nested = {"group": {"attack_id": "G0016"}, "cves": [{"cve_id": "CVE-1", "name": "x"}], "vendor_key": "msft",
              "other": {"cwe_id": "CWE-79", "product_key": "a:b"}, "attack_id": None}
    assert collect_ids(nested) == {"G0016", "CVE-1", "msft", "CWE-79", "a:b"}
    short = compact({"items": list(range(tools.LIST_CAP + 5)), "text": "x" * 1000})
    assert short["items"][-1] == "... 5 more not shown" and len(short["items"]) == tools.LIST_CAP + 1
    assert len(short["text"]) == tools.TEXT_CAP + 3


def test_search_entities_lowercases_and_cites_matches():
    driver = FakeDriver(lambda query, parameters: [{"kind": "Group", "id": "G0016", "name": "APT29"}])
    out = call_tool(driver, "search_entities", {"text": "Cozy Bear"})
    assert out.data == {"matches": [{"kind": "Group", "id": "G0016", "name": "APT29"}]}
    assert out.verified_ids == {"G0016"} and driver.queries[0][1] == {"term": "cozy bear", "limit": 5}


def test_group_techniques_summarizes_mitigations():
    out = call_tool(answering({groups.GROUP_TECHNIQUES_QUERY: [GROUP_RECORD]}), "group_techniques",
                    {"group_id": "G0016"})
    assert out.data["top_mitigations"] == [{"attack_id": "M1026", "name": "PAM", "covers_techniques": 1}]
    assert "procedure" not in out.data["techniques"][0]
    assert {"G0016", "T1003.002", "M1026"} <= out.verified_ids and not out.inferred_ids


SUGGESTED = {"attack_id": "T1059", "name": "Command and Scripting Interpreter", "confidence": 0.8,
             "model": "random_forest", "model_version": "rf-1"}


def test_cve_groups_keeps_suggestions_out_of_the_verified_ids():
    driver = answering({cves.CVE_GROUPS_QUERY: [CVE_RECORD],
                        cves.SUGGESTIONS_QUERY: [{"status": "stored", "suggestions": [SUGGESTED]}]})
    out = call_tool(driver, "cve_groups", {"cve_id": "CVE-2021-44228"})
    assert out.inferred_ids == {"T1059"}
    assert "T1059" not in out.verified_ids and {"CVE-2021-44228", "T1190", "G0034"} <= out.verified_ids


@pytest.mark.parametrize("name, arguments, mapping, expected", [
    ("technique_cves", {"technique_id": "T1059", "ransomware": True},
     {techniques.TECHNIQUE_CVES_QUERY: [TECHNIQUE_RECORD]}, {"T1059", "CVE-2013-3346"}),
    ("top_exploited", {"level": "vendor"}, {products.TOP_VENDORS_QUERY: [VENDOR_RECORD]}, {"microsoft", "CWE-787"}),
    ("top_exploited", {"level": "product"}, {products.TOP_PRODUCTS_QUERY: [PRODUCT_RECORD]}, {"fortinet:fortios"}),
    ("product_exposure", {"product_key": "fortinet:fortios"}, {products.EXPOSURE_QUERY: [EXPOSURE_RECORD]},
     {"fortinet:fortios", "CVE-2018-13379", "T1190", "G0096", "M1032"}),
])
def test_fixed_tools_cite_what_they_return(name, arguments, mapping, expected):
    out = call_tool(answering(mapping), name, arguments)
    assert expected <= out.verified_ids and out.path and out.source


def test_technique_cves_drops_mapping_comments():
    out = call_tool(answering({techniques.TECHNIQUE_CVES_QUERY: [TECHNIQUE_RECORD]}), "technique_cves",
                    {"technique_id": "T1059"})
    assert "mapping_comment" not in out.data["cves"][0]


def test_analytics_tools(monkeypatch):
    monkeypatch.setattr(analytics, "mitigation_plan", lambda driver, since, max_picks: analytics.MitigationPlanResponse(
        scope={"since": since, "kev_cves": 1, "mapped_cves": 1}, weighting="w", reachable_techniques=1, total_weight=1,
        covered_pct=100, picks=[{"rank": 1, "attack_id": "M1026", "name": "PAM", "gain": 1,
                                 "newly_covered_techniques": 1, "cumulative_weight": 1, "cumulative_pct": 100}],
        uncoverable={"technique_count": 0, "weight": 0, "pct": 0, "techniques": []}, guarantee="g"))
    out = call_tool(FakeDriver(), "mitigation_plan", {"since": "2025-01-01", "max_picks": 3})
    assert out.verified_ids == {"M1026"} and out.data["scope"]["since"] == "2025-01-01"
    monkeypatch.setattr(analytics, "central_techniques", lambda driver, by, limit: None)
    with pytest.raises(ToolFailure, match="make analytics"):
        call_tool(FakeDriver(), "central_techniques", {"by": "betweenness"})


@pytest.mark.parametrize("name, arguments", [
    ("group_techniques", {"group_id": "G9999"}),
    ("technique_cves", {"technique_id": "T9999"}),
    ("cve_groups", {"cve_id": "CVE-1999-0001"}),
    ("product_exposure", {"product_key": "nope:nope"}),
    ("similar_groups", {"group_id": "G9999"}),
])
def test_unknown_ids_are_tool_failures_that_point_to_search(name, arguments):
    with pytest.raises(ToolFailure):
        call_tool(FakeDriver(), name, arguments)


def guarded(rows):
    return FakeSessionDriver(session_responder=lambda query, parameters: {"rows": rows})


def test_run_cypher_cites_ids_in_rows_and_literals():
    driver = guarded([{"n": 34, "example": "CVE-2020-0001", "label": "Microsoft"}])
    out = call_tool(driver, "run_cypher", {"query": "MATCH (c:CVE)-[:HAS_WEAKNESS]->(:CWE {cwe_id: 'CWE-79'}) "
                                                    "RETURN count(c) AS n, 'CVE-2020-0001' AS example"})
    assert out.verified_ids == {"CWE-79", "CVE-2020-0001"} and out.rows == 1
    assert out.cypher.endswith("LIMIT 50") and out.data["row_cap"] == 50


def test_run_cypher_on_model_links_marks_everything_model_generated():
    out = call_tool(guarded([{"t": "T1059"}]), "run_cypher",
                    {"query": "MATCH (:CVE)-[:INFERRED_MAPS_TO]->(t:Technique) RETURN t.attack_id AS t"})
    assert out.inferred_ids == {"T1059"} and not out.verified_ids


def test_run_cypher_rejections_propagate():
    with pytest.raises(GuardrailError):
        call_tool(guarded([]), "run_cypher", {"query": "MATCH (n) DETACH DELETE n"})
