"""Tests for GET /paths/connection (D20), with a fake driver standing in for Neo4j."""
# pylint: disable=missing-function-docstring

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_driver
from app.main import app
from app.services import paths
from tests.fakes import FakeDriver

client = TestClient(app)

GROUP = {"attack_id": "G0025", "name": "APT17"}
PRODUCT = {"product_key": "microsoft:exchange_server", "name": "exchange_server"}
NODES = [
    {"labels": ["Group"], "id": "G0025", "name": "APT17"},
    {"labels": ["Software", "Malware"], "id": "S0069", "name": "BLACKCOFFEE"},
    {"labels": ["Technique", "SubTechnique"], "id": "T1059.003", "name": "Windows Command Shell"},
    {"labels": ["Technique"], "id": "T1059", "name": "Command and Scripting Interpreter"},
    {"labels": ["CVE"], "id": "CVE-2021-42321", "name": "Exchange RCE"},
    {"labels": ["Product"], "id": "microsoft:exchange_server", "name": "exchange_server"},
]
RELATIONSHIPS = [
    {"type": "USES", "start": "G0025"},
    {"type": "USES", "start": "S0069"},
    {"type": "SUBTECHNIQUE_OF", "start": "T1059.003"},
    {"type": "PRIMARY_IMPACT", "start": "CVE-2021-42321"},
    {"type": "AFFECTS", "start": "CVE-2021-42321"},
]
PATH_RECORD = {"group": GROUP, "product": PRODUCT, "nodes": NODES, "relationships": RELATIONSHIPS}


@pytest.fixture(name="answer")
def fixture_answer():
    """Serve the given record (or none) to every query, and return the driver to inspect what was sent."""
    def install(record):
        driver = FakeDriver(lambda query, parameters: [record] if record else [])
        app.dependency_overrides[get_driver] = lambda: driver
        return driver
    yield install
    app.dependency_overrides.clear()


def get(query):
    return client.get("/paths/connection?" + query)


def test_path_is_ordered_with_directions_and_reading(answer):
    driver = answer(PATH_RECORD)
    response = get("group=G0025&product=microsoft:exchange_server")
    assert response.status_code == 200
    body = response.json()
    assert [n["kind"] for n in body["nodes"]] == ["Group", "Software", "Technique", "Technique", "CVE", "Product"]
    assert [r["direction"] for r in body["relationships"]] == ["forward"] * 3 + ["backward", "forward"]
    assert body["hops"] == 5 and body["max_hops"] == 6 and "association" in body["note"]
    assert body["reading"].startswith(
        "APT17 (G0025) shares technique Command and Scripting Interpreter (T1059) with Exchange RCE "
        "(CVE-2021-42321) affecting exchange_server (microsoft:exchange_server), reached through BLACKCOFFEE")
    assert "Exchange RCE (CVE-2021-42321) is mapped to Command and Scripting Interpreter (T1059) (primary impact)" \
        in body["reading"]
    assert "exploits" not in body["reading"]
    query, parameters, kwargs = driver.queries[0]
    assert "INFERRED_MAPS_TO" not in query and "*..8" in query and "shortestPath" in query
    assert parameters["bridge_types"] == ["EXPLOITS_VIA", "PRIMARY_IMPACT", "SECONDARY_IMPACT"]
    assert kwargs["routing_"] == "r"


def test_direct_path_has_no_reached_through(answer):
    answer({"group": GROUP, "product": PRODUCT, "nodes": [NODES[0], NODES[3], NODES[4], NODES[5]],
            "relationships": [RELATIONSHIPS[0], {"type": "EXPLOITS_VIA", "start": "CVE-2021-42321"},
                              RELATIONSHIPS[4]]})
    reading = get("group=G0025&product=microsoft:exchange_server").json()["reading"]
    assert "reached through" not in reading and "(exploitation)" in reading


@pytest.mark.parametrize("record, query, detail", [
    (None, "group=G0025&product=a:b", "Group G0025 not found"),
    ({"group": None, "product": None, "nodes": None}, "group=G0025&product=a:b", "Group G0025 not found"),
    ({"group": GROUP, "product": None, "nodes": None}, "group=G0025&product=a:b", "Product a:b not found"),
    ({"group": GROUP, "product": PRODUCT, "nodes": None, "relationships": None}, "group=G0025&product=a:b",
     "No verified path from G0025 to a:b within 8 hops"),
    (PATH_RECORD, "group=G0025&product=a:b&max_hops=4", "within 4 hops; the shortest verified path has 5"),
])
def test_not_found_cases_are_404_with_a_clear_message(answer, record, query, detail):
    answer(record)
    response = get(query)
    assert response.status_code == 404 and detail in response.json()["detail"]


@pytest.mark.parametrize("query", [
    "group=APT17&product=a:b", "group=G0025", "product=a:b",
    "group=G0025&product=a:b&max_hops=0", "group=G0025&product=a:b&max_hops=9",
])
def test_bad_input_is_422(answer, query):
    answer(PATH_RECORD)
    assert get(query).status_code == 422


def test_unexpected_node_kind_is_rejected():
    with pytest.raises(ValueError, match="unexpected node"):
        paths.node_kind(["Campaign"])
