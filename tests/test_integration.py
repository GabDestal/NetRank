"""End-to-end checks against a real, loaded Neo4j (make docker-run, make ingest).

Skipped unless THREATGRAPH_INTEGRATION=1, so CI and plain `make test` never need a database.
These catch what fake drivers cannot: Cypher syntax errors and queries that return the wrong shape.
Run with: make test-integration
"""
# pylint: disable=missing-function-docstring

import os

import pytest
from fastapi.testclient import TestClient

from app.database.connection import close_driver, get_driver
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("THREATGRAPH_INTEGRATION") != "1",
                                reason="set THREATGRAPH_INTEGRATION=1 with Neo4j running and loaded")


@pytest.fixture(name="client", scope="module")
def fixture_client():
    with TestClient(app) as test_client:
        yield test_client
    close_driver()


def get_ok(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_database_is_reachable(client):
    assert get_ok(client, "/health/db")["status"] == "ok"


def test_question_1_group_techniques(client):
    body = get_ok(client, "/groups/G0016/techniques")
    assert body["group"]["name"] == "APT29" and body["technique_count"] > 0
    assert all(t["tactics"] for t in body["techniques"])


def test_question_2_technique_cves(client):
    with_subs = get_ok(client, "/techniques/T1059/cves")["cve_count"]
    without = get_ok(client, "/techniques/T1059/cves?include_subtechniques=false")["cve_count"]
    assert with_subs >= without > 0
    ransomware = get_ok(client, "/techniques/T1190/cves?ransomware=true")["cves"]
    assert ransomware and all(c["known_ransomware_use"] for c in ransomware)


def test_question_3_cve_groups(client):
    body = get_ok(client, "/cves/CVE-2021-44228/groups?limit=5")
    assert body["techniques"] and len(body["groups"]) <= 5 <= body["group_count"]


def test_question_4_rankings(client):
    vendors = get_ok(client, "/vendors/top?limit=3")["vendors"]
    assert len(vendors) == 3 and vendors[0]["exploited_cves"] >= vendors[1]["exploited_cves"]
    assert get_ok(client, "/products/top?limit=3")["products"][0]["top_weaknesses"]


def test_question_7_exposure(client):
    key = get_ok(client, "/products?search=fortios")["products"][0]["product_key"]
    body = get_ok(client, f"/products/exposure?product={key}")
    assert body["cve_count"] >= body["mapped_cve_count"] > 0
    assert body["techniques"] and body["groups"] and body["mitigations"]


def test_question_5_mitigation_plan(client):
    body = get_ok(client, "/mitigations/plan")
    assert body["picks"] and body["picks"][0]["cumulative_pct"] > 0
    assert body["covered_pct"] + body["uncoverable"]["pct"] == pytest.approx(100, abs=0.2)
    assert body["uncoverable"]["technique_count"] == len(body["uncoverable"]["techniques"])
    recent = get_ok(client, "/mitigations/plan?since=2025-01-01&max_picks=2")
    assert recent["scope"]["kev_cves"] < body["scope"]["kev_cves"] and len(recent["picks"]) == 2


def test_question_6_central_techniques(client):
    by_degree = get_ok(client, "/techniques/central?limit=5")["techniques"]
    assert by_degree[0]["used_by_groups"] >= by_degree[-1]["used_by_groups"]
    body = get_ok(client, "/techniques/central?by=betweenness&limit=5")
    assert body["techniques"][0]["betweenness"] >= body["techniques"][-1]["betweenness"]
    assert body["communities"] and body["analytics"]["modularity"] > 0


def test_group_similarity_runs_gds_live_and_cleans_up(client):
    body = get_ok(client, "/groups/G0016/similar?limit=5")
    assert 0 < len(body["similar"]) <= 5
    scores = [g["jaccard"] for g in body["similar"]]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)
    assert all(g["attack_id"] != "G0016" for g in body["similar"])
    records, _, _ = get_driver().execute_query("CALL gds.graph.list() YIELD graphName RETURN collect(graphName) AS g")
    assert not [name for name in records[0]["g"] if name.startswith("group_similarity_")]


def test_cve_suggestions_are_separate_and_labelled(client):
    body = get_ok(client, "/cves/CVE-2021-44228/groups")
    assert body["suggestions_label"] == "model-generated, not verified"
    verified = {t["attack_id"] for t in body["techniques"]}
    assert not verified & {s["attack_id"] for s in body["suggested_techniques"]}


def test_unknown_ids_are_404(client):
    assert client.get("/groups/G9999/techniques").status_code == 404
    assert client.get("/products/exposure?product=nope:nope").status_code == 404
