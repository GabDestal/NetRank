"""Tests for the question endpoints, with a fake driver standing in for Neo4j."""
# pylint: disable=missing-function-docstring

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import CypherSyntaxError, ServiceUnavailable

from app.database.connection import get_driver
from app.main import app
from app.models.common import SHARED_TECHNIQUE_NOTE
from app.services import cves, groups, products, techniques
from tests.fakes import FakeDriver

client = TestClient(app)

GROUP_RECORD = {
    "group": {"attack_id": "G0016", "name": "APT29", "aliases": ["Cozy Bear"]},
    "techniques": [{"attack_id": "T1003.002", "name": "Security Account Manager", "is_subtechnique": True,
                    "tactics": ["Credential Access"], "mitigations": [{"attack_id": "M1026", "name": "PAM"}],
                    "procedure": "APT29 used reg save", "references": ["Report (https://r.test)"]}],
}
TECHNIQUE_RECORD = {
    "technique": {"attack_id": "T1059", "name": "Command and Scripting Interpreter"},
    "cves": [{"cve_id": "CVE-2013-3346", "name": "Reader bug", "cvss_score": 9.3, "cvss_source_type": "Primary",
              "known_ransomware_use": False, "date_added": "2022-03-03", "mapped_technique": "T1059.001",
              "mapping_comment": "scripts"}],
}
CVE_RECORD = {
    "cve": {"cve_id": "CVE-2021-44228", "name": "Log4Shell", "cvss_score": 10.0, "cvss_source_type": "Primary",
            "known_ransomware_use": True},
    "techniques": [{"attack_id": "T1190", "name": "Exploit Public-Facing Application", "mapping_type": "EXPLOITS_VIA"}],
    "group_count": 80,
    "groups": [{"attack_id": "G0034", "name": "Sandworm Team", "shared_techniques": ["T1190"]}],
}
VENDOR_RECORD = {"vendor_key": "microsoft", "name": "microsoft", "exploited_cves": 405, "ransomware_cves": 117,
                 "top_weaknesses": [{"cwe_id": "CWE-787", "cves": 58}]}
PRODUCT_RECORD = {"product_key": "fortinet:fortios", "name": "fortios", "vendor": "fortinet", "exploited_cves": 20,
                  "ransomware_cves": 13, "top_weaknesses": []}
EXPOSURE_RECORD = {
    "product": {"product_key": "fortinet:fortios", "name": "fortios", "part": "o", "vendor": "fortinet"},
    "cves": [
        {"cve_id": "CVE-2022-0001", "name": "low", "cvss_score": None, "cvss_source_type": None,
         "known_ransomware_use": False, "mapped_to_attack": False},
        {"cve_id": "CVE-2018-13379", "name": "high", "cvss_score": 9.8, "cvss_source_type": "Primary",
         "known_ransomware_use": True, "mapped_to_attack": True},
    ],
    "techniques": [{"attack_id": "T1190", "name": "Exploit Public-Facing Application", "via_cves": 1,
                    "mapping_types": ["EXPLOITS_VIA"]}],
    "groups": [{"attack_id": "G0096", "name": "APT41", "shared_techniques": 1}],
    "mitigations": [{"attack_id": "M1032", "name": "Multi-factor Authentication", "covers_techniques": 1}],
}


@pytest.fixture(name="serve")
def fixture_serve():
    """Install a fake driver answering every query with the given records."""
    driver_holder = {}

    def install(records):
        driver = FakeDriver(lambda query, parameters: records)
        driver_holder["driver"] = driver
        app.dependency_overrides[get_driver] = lambda: driver
        return driver

    yield install
    app.dependency_overrides.clear()


def last_call(driver):
    return driver.queries[-1]


def test_group_techniques(serve):
    driver = serve([GROUP_RECORD])
    response = client.get("/groups/G0016/techniques")
    assert response.status_code == 200
    body = response.json()
    assert body["technique_count"] == 1
    assert body["techniques"][0]["mitigations"] == [{"attack_id": "M1026", "name": "PAM"}]
    query, params, _ = last_call(driver)
    assert query == groups.GROUP_TECHNIQUES_QUERY and params == {"group_id": "G0016"}


def test_technique_cves_passes_filters(serve):
    driver = serve([TECHNIQUE_RECORD])
    body = client.get("/techniques/T1059/cves?ransomware=false&include_subtechniques=false").json()
    assert body["cve_count"] == 1 and body["include_subtechniques"] is False
    assert body["cves"][0]["date_added"] == "2022-03-03"
    _, params, _ = last_call(driver)
    assert params == {"technique_id": "T1059", "ransomware": False, "include_subtechniques": False}


def test_technique_cves_defaults(serve):
    driver = serve([TECHNIQUE_RECORD])
    client.get("/techniques/T1059.001/cves")
    assert last_call(driver)[1] == {"technique_id": "T1059.001", "ransomware": None, "include_subtechniques": True}
    assert last_call(driver)[0] == techniques.TECHNIQUE_CVES_QUERY


def test_cve_groups_carries_the_association_note(serve):
    driver = serve([CVE_RECORD])
    body = client.get("/cves/CVE-2021-44228/groups?limit=5").json()
    assert body["association"] == "shared_technique" and body["note"] == SHARED_TECHNIQUE_NOTE
    assert body["group_count"] == 80 and body["groups"][0]["shared_techniques"] == ["T1190"]
    query, params, _ = last_call(driver)
    assert query == cves.CVE_GROUPS_QUERY and params == {"cve_id": "CVE-2021-44228", "limit": 5}
    assert "INFERRED" not in query


@pytest.mark.parametrize("url, record, key", [
    ("/vendors/top?limit=2&cwe_limit=1", VENDOR_RECORD, "vendors"),
    ("/products/top?limit=2&cwe_limit=1", PRODUCT_RECORD, "products"),
])
def test_rankings(serve, url, record, key):
    driver = serve([record])
    body = client.get(url).json()
    assert body[key][0]["exploited_cves"] == record["exploited_cves"]
    assert last_call(driver)[1] == {"limit": 2, "cwe_limit": 1}


def test_product_search_lowercases_the_term(serve):
    driver = serve([{"product_key": "fortinet:fortios", "name": "fortios", "vendor": "fortinet",
                     "exploited_cves": 20}])
    body = client.get("/products?search=FortiOS").json()
    assert body["products"][0]["product_key"] == "fortinet:fortios"
    query, params, _ = last_call(driver)
    assert query == products.PRODUCT_SEARCH_QUERY and params == {"term": "fortios", "limit": 20}


def test_product_exposure_sorts_cves_and_counts(serve):
    driver = serve([EXPOSURE_RECORD])
    body = client.get("/products/exposure?product=fortinet:fortios&limit=3").json()
    assert [c["cve_id"] for c in body["cves"]] == ["CVE-2018-13379", "CVE-2022-0001"]
    assert body["cve_count"] == 2 and body["mapped_cve_count"] == 1 and body["technique_count"] == 1
    assert body["note"] == SHARED_TECHNIQUE_NOTE
    assert last_call(driver)[1] == {"product_key": "fortinet:fortios", "limit": 3}


@pytest.mark.parametrize("url", [
    "/groups/G9999/techniques",
    "/techniques/T9999/cves",
    "/cves/CVE-1999-0001/groups",
    "/products/exposure?product=nope:nope",
])
def test_unknown_ids_are_404(serve, url):
    serve([])
    response = client.get(url)
    assert response.status_code == 404
    assert "not" in response.json()["detail"]


@pytest.mark.parametrize("url", [
    "/groups/APT29/techniques",
    "/techniques/T59/cves",
    "/techniques/T1059.1/cves",
    "/cves/log4shell/groups",
    "/cves/CVE-2021-44228/groups?limit=0",
    "/vendors/top?limit=1000",
    "/products?search=x",
    "/products/exposure",
])
def test_malformed_input_is_422_before_any_query(serve, url):
    driver = serve([])
    assert client.get(url).status_code == 422
    assert not driver.queries


@pytest.mark.parametrize("error", [ServiceUnavailable("bolt://secret:7687 down"),
                                   CypherSyntaxError("bad query text")])
def test_neo4j_errors_are_503_without_details(error):
    def responder(query, parameters):
        raise error

    app.dependency_overrides[get_driver] = lambda: FakeDriver(responder)
    try:
        response = client.get("/vendors/top")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"detail": "Neo4j is unavailable"}


def test_every_query_is_read_only():
    read_queries = [groups.GROUP_TECHNIQUES_QUERY, techniques.TECHNIQUE_CVES_QUERY, cves.CVE_GROUPS_QUERY,
                    products.TOP_VENDORS_QUERY, products.TOP_PRODUCTS_QUERY, products.PRODUCT_SEARCH_QUERY,
                    products.EXPOSURE_QUERY]
    for query in read_queries:
        for keyword in ("CREATE", "MERGE", "DELETE", "SET ", "REMOVE", "DROP"):
            assert keyword not in query.upper()
