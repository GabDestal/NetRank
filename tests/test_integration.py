"""End-to-end checks against a real, loaded Neo4j (make docker-run, make ingest).

Skipped unless THREATGRAPH_INTEGRATION=1, so CI and plain `make test` never need a database.
These catch what fake drivers cannot: Cypher syntax errors and queries that return the wrong shape.
Run with: make test-integration
"""
# pylint: disable=missing-function-docstring

import os

import pytest
from fastapi.testclient import TestClient

from app.database.connection import close_driver
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


def test_unknown_ids_are_404(client):
    assert client.get("/groups/G9999/techniques").status_code == 404
    assert client.get("/products/exposure?product=nope:nope").status_code == 404
