"""Tests for the graph-algorithm endpoints: /techniques/central, /groups/{id}/similar, /mitigations/plan."""
# pylint: disable=missing-function-docstring

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ClientError

from app.database.connection import get_driver
from app.main import app
from app.services import analytics
from tests.fakes import FakeDriver

client = TestClient(app)

ANALYTICS = {"gds_version": "2.13.14", "computed_at": "2026-10-15T17:40:27Z", "parameters": "{}",
             "community_count": 317, "modularity": 0.566}
CENTRAL_RECORD = {
    "analytics": ANALYTICS,
    "techniques": [{"attack_id": "T1105", "name": "Ingress Tool Transfer", "used_by_groups": 90,
                    "betweenness": 1725.3, "community": 418, "community_size": 115}],
    "communities": [{"community": 418, "size": 115, "top_techniques": ["Ingress Tool Transfer"]}],
}
APT29 = {"attack_id": "G0016", "name": "APT29", "aliases": ["Cozy Bear"]}
SIMILAR = [{"attack_id": "G0007", "name": "APT28", "jaccard": 0.223, "shared_techniques": 29,
            "techniques_used": 93}]


def use(driver):
    app.dependency_overrides[get_driver] = lambda: driver
    return driver


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def queries(driver):
    return [query for query, _, _ in driver.queries]


# ---------- /techniques/central (question 6, stored results) ----------

def test_central_techniques():
    driver = use(FakeDriver(lambda query, parameters: [CENTRAL_RECORD]))
    body = client.get("/techniques/central?by=betweenness&limit=5&community_limit=2").json()
    assert body["ranked_by"] == "betweenness" and body["analytics"]["community_count"] == 317
    assert body["techniques"][0]["attack_id"] == "T1105"
    assert body["communities"][0]["size"] == 115
    assert driver.queries[0][1] == {"by": "betweenness", "limit": 5, "community_limit": 2, "members": 5,
                                    "min_community_size": 5}


def test_central_techniques_without_analytics_is_503():
    use(FakeDriver())
    response = client.get("/techniques/central")
    assert response.status_code == 503
    assert "make analytics" in response.json()["detail"]


def test_central_techniques_rejects_unknown_ranking():
    driver = use(FakeDriver())
    assert client.get("/techniques/central?by=pagerank").status_code == 422
    assert not driver.queries


# ---------- /groups/{id}/similar (D17, live GDS) ----------

def similarity_driver(fail=False):
    def responder(query, _parameters):
        if query == analytics.GROUP_PROFILE_QUERY:
            return [{"group": APT29, "techniques_used": 66}]
        if query == analytics.SIMILAR_GROUPS_QUERY:
            if fail:
                raise ClientError("algorithm failed")
            return SIMILAR
        return []

    return FakeDriver(responder)


def test_similar_groups_projects_runs_and_drops():
    driver = use(similarity_driver())
    body = client.get("/groups/G0016/similar?limit=3").json()
    assert body["group"]["name"] == "APT29" and body["techniques_used"] == 66
    assert body["similar"] == SIMILAR and "Jaccard" in body["method"]
    assert queries(driver) == [analytics.GROUP_PROFILE_QUERY, analytics.SIMILARITY_PROJECTION,
                               analytics.SIMILAR_GROUPS_QUERY, analytics.DROP_PROJECTION]
    graphs = {params["graph"] for _, params, _ in driver.queries[1:]}
    assert len(graphs) == 1 and graphs.pop().startswith("group_similarity_")
    assert driver.queries[2][1]["limit"] == 3 and driver.queries[2][1]["group_id"] == "G0016"


def test_similar_groups_uses_a_new_projection_name_per_request():
    driver = use(similarity_driver())
    client.get("/groups/G0016/similar")
    client.get("/groups/G0016/similar")
    names = [params["graph"] for query, params, _ in driver.queries if query == analytics.SIMILARITY_PROJECTION]
    assert len(names) == 2 and names[0] != names[1]


def test_similar_groups_drops_the_projection_when_the_algorithm_fails():
    driver = use(similarity_driver(fail=True))
    assert client.get("/groups/G0016/similar").status_code == 503
    assert queries(driver)[-1] == analytics.DROP_PROJECTION


def test_similar_groups_unknown_group_is_404_without_projecting():
    driver = use(FakeDriver())
    assert client.get("/groups/G9999/similar").status_code == 404
    assert queries(driver) == [analytics.GROUP_PROFILE_QUERY]


def test_similar_groups_validates_input():
    driver = use(FakeDriver())
    assert client.get("/groups/APT29/similar").status_code == 422
    assert client.get("/groups/G0016/similar?limit=0").status_code == 422
    assert not driver.queries


# ---------- /mitigations/plan (question 5, greedy cover) ----------

def technique(attack_id, weight, *mitigations):
    return {"attack_id": attack_id, "name": f"name {attack_id}", "weight": weight,
            "mitigations": [{"attack_id": m, "name": f"name {m}"} for m in mitigations]}


TECHNIQUES = [
    technique("T1", 10, "M1", "M2"),
    technique("T2", 6, "M2"),
    technique("T3", 5, "M3"),
    technique("T4", 3, "M1", "M3"),
    technique("T5", 2),
]


def test_greedy_cover_picks_by_uncovered_weight():
    picks, uncovered = analytics.greedy_cover(TECHNIQUES)
    assert [(p["attack_id"], p["gain"], p["cumulative_weight"]) for p in picks] == [
        ("M2", 16, 16),  # T1 + T2
        ("M3", 8, 24),   # T3 + T4; M1 would only add T4 now
    ]
    assert uncovered == {"T5"}


def test_greedy_cover_breaks_ties_by_lowest_id_and_respects_max_picks():
    tied = [technique("T1", 4, "M9"), technique("T2", 4, "M2")]
    picks, uncovered = analytics.greedy_cover(tied, max_picks=1)
    assert [p["attack_id"] for p in picks] == ["M2"] and uncovered == {"T1"}


def test_greedy_cover_with_nothing_to_cover():
    assert analytics.greedy_cover([]) == ([], set())


def plan_driver(rows, scope=None):
    def responder(query, _parameters):
        if query == analytics.PLAN_WEIGHTS_QUERY:
            return rows
        return [scope or {"kev_cves": 100, "mapped_cves": 40}]

    return FakeDriver(responder)


def test_mitigation_plan_lists_uncoverable_techniques():
    use(plan_driver(TECHNIQUES))
    body = client.get("/mitigations/plan").json()
    assert body["total_weight"] == 26 and body["reachable_techniques"] == 5
    assert [p["attack_id"] for p in body["picks"]] == ["M2", "M3"]
    assert body["picks"][1]["cumulative_pct"] == 92.3 and body["covered_pct"] == 92.3
    assert body["uncoverable"] == {"technique_count": 1, "weight": 2, "pct": 7.7,
                                   "techniques": [{"attack_id": "T5", "name": "name T5", "weight": 2}]}
    assert "1 - 1/e" in body["guarantee"]


def test_mitigation_plan_passes_since_and_max_picks():
    driver = use(plan_driver(TECHNIQUES))
    body = client.get("/mitigations/plan?since=2025-01-01&max_picks=1").json()
    assert body["scope"] == {"since": "2025-01-01", "kev_cves": 100, "mapped_cves": 40}
    assert len(body["picks"]) == 1 and body["covered_pct"] == 61.5
    assert all(params == {"since": "2025-01-01"} for _, params, _ in driver.queries)


def test_mitigation_plan_with_no_mapped_cves():
    use(plan_driver([], {"kev_cves": 3, "mapped_cves": 0}))
    body = client.get("/mitigations/plan?since=2030-01-01").json()
    assert body["total_weight"] == 0 and body["picks"] == [] and body["covered_pct"] == 0.0


def test_mitigation_plan_validates_input():
    driver = use(FakeDriver())
    assert client.get("/mitigations/plan?since=yesterday").status_code == 422
    assert client.get("/mitigations/plan?max_picks=0").status_code == 422
    assert not driver.queries


def test_api_queries_never_write_to_the_database():
    for query in (analytics.CENTRAL_QUERY, analytics.GROUP_PROFILE_QUERY, analytics.SIMILAR_GROUPS_QUERY,
                  analytics.PLAN_WEIGHTS_QUERY, analytics.PLAN_SCOPE_QUERY):
        for keyword in ("CREATE", "MERGE", "DELETE", "SET ", "REMOVE", ".write(", ".mutate("):
            assert keyword not in query
