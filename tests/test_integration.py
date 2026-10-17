"""End-to-end checks against a real, loaded Neo4j (make docker-run, make ingest).

Part of `make test`. When Neo4j is not reachable (as in CI) or holds no data, every test here is
skipped with the reason, so the suite stays green without a database.
These catch what fake drivers cannot: Cypher syntax errors and queries that return the wrong shape.
Run only these with: make test-integration
"""
# pylint: disable=missing-function-docstring

import pytest
from fastapi.testclient import TestClient
from neo4j import READ_ACCESS, GraphDatabase
from neo4j.exceptions import ClientError, DriverError, Neo4jError

from app.agent.guardrails import MAX_ROWS, run_guarded
from app.config import load_settings
from app.database.connection import close_driver, get_driver
from app.main import app


def neo4j_skip_reason() -> str | None:
    """Return why these tests cannot run here, or None if Neo4j is up and loaded."""
    settings = load_settings()
    try:
        # Short timeouts and no retries, so a missing database costs seconds, not the driver's 30 s retry loop.
        with GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password),
                                  connection_timeout=3, connection_acquisition_timeout=3,
                                  max_transaction_retry_time=0) as driver:
            records, _, _ = driver.execute_query("MATCH (m:ImportMeta) RETURN count(m) AS n")
    except (DriverError, Neo4jError, OSError, ValueError) as exc:
        return f"Neo4j not reachable at {settings.neo4j_uri} ({type(exc).__name__}); start it with make docker-run"
    if records[0]["n"] == 0:
        return "Neo4j is reachable but empty; run make ingest"
    return None


SKIP_REASON = neo4j_skip_reason()
pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


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


def test_guardrails_against_the_real_server(client):
    check = client.post("/agent/check-cypher", json={"query": "MATCH (c:CVE) RETURN c.cve_id"}).json()
    assert check["allowed"] and check["query"].endswith("LIMIT 50")
    unknown = client.post("/agent/check-cypher", json={"query": "MATCH (v:Vulnerability) RETURN v"}).json()
    assert unknown["rule"] == "explain_unknown_schema" and "Vulnerability" in unknown["reason"]
    bad = client.post("/agent/check-cypher", json={"query": "MATCH (c:CVE) RETURN c.cve_id ORDER BY"}).json()
    assert bad["rule"] == "explain_syntax"


def test_guarded_cypher_runs_read_only_with_the_limit():
    result = run_guarded(get_driver(), "MATCH (c:CVE)-[:HAS_WEAKNESS]->(:CWE {cwe_id: 'CWE-79'}) RETURN c.cve_id AS id")
    assert 0 < len(result.rows) <= MAX_ROWS and result.query.endswith(f"LIMIT {MAX_ROWS}")
    with get_driver().session(default_access_mode=READ_ACCESS) as session, pytest.raises(ClientError):
        session.run("MATCH (c:CVE {cve_id: 'CVE-2021-44228'}) SET c.probe = 1 RETURN c").consume()
