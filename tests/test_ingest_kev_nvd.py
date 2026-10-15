"""Tests for scripts.ingest_kev_nvd, on small hand-built KEV and NVD records."""
# pylint: disable=missing-function-docstring

import json

import pytest
from neo4j.exceptions import ServiceUnavailable

from scripts import common, ingest_kev_nvd
from scripts.download import KEV, NVD_FILENAME
from tests.fakes import FakeDriver


def metric(version, score, source_type, source="nvd@nist.gov", v2=False):
    data = {"version": version, "baseScore": score, "vectorString": f"CVSS:{version}/AV:N"}
    if v2:
        return {"source": source, "type": source_type, "cvssData": data, "baseSeverity": "HIGH"}
    return {"source": source, "type": source_type, "cvssData": data | {"baseSeverity": "CRITICAL"}}


def cpe_match(criteria, match_id, vulnerable=True, **ranges):
    return {"criteria": criteria, "matchCriteriaId": match_id, "vulnerable": vulnerable, **ranges}


KEV_CATALOG = {
    "catalogVersion": "2026.10.14",
    "vulnerabilities": [
        {"cveID": "CVE-2021-44228", "vendorProject": "Apache", "product": "Log4j2", "vulnerabilityName": "Log4Shell",
         "dateAdded": "2021-12-10", "dueDate": "2021-12-24", "shortDescription": "JNDI injection",
         "requiredAction": "Patch", "knownRansomwareCampaignUse": "Known", "cwes": ["CWE-20", "CWE-917"]},
        {"cveID": "CVE-2024-0001", "vendorProject": "Acme", "product": "Widget", "vulnerabilityName": "Widget bug",
         "dateAdded": "2024-02-01", "dueDate": "2024-02-22", "knownRansomwareCampaignUse": "Unknown", "cwes": []},
        {"cveID": "CVE-2024-0002", "vendorProject": "Acme", "product": "Gadget", "dateAdded": "2024-03-01",
         "knownRansomwareCampaignUse": "Unknown"},
    ],
}

NVD_CVES = [
    {"id": "CVE-2021-44228", "published": "2021-12-10T10:15:09.143", "lastModified": "2025-02-04T14:25:34.416",
     "metrics": {
         "cvssMetricV31": [metric("3.1", 9.0, "Secondary", "security@apache.org"), metric("3.1", 10.0, "Primary")],
         "cvssMetricV2": [metric("2.0", 9.3, "Primary", v2=True)],
         "ssvcV203": [{"ssvcData": {"options": [{"exploitation": "active"}, {"automatable": "yes"},
                                                {"technicalImpact": "total"}]}}]},
     "weaknesses": [{"source": "nvd@nist.gov", "description": [{"value": "CWE-917"}]},
                    {"source": "security@apache.org", "description": [{"value": "CWE-502"},
                                                                       {"value": "NVD-CWE-noinfo"}]}],
     "configurations": [{"nodes": [{"cpeMatch": [
         cpe_match("cpe:2.3:a:apache:log4j:*:*:*:*:*:*:*:*", "m1", versionStartIncluding="2.0",
                   versionEndExcluding="2.15.0"),
         cpe_match("cpe:2.3:a:apache:log4j:2.0:beta9:*:*:*:*:*:*", "m2"),
         cpe_match("cpe:2.3:a:apache:log4j:2.0:beta9:*:*:*:*:*:*", "m2"),
     ]}, {"cpeMatch": [cpe_match("cpe:2.3:o:linux:linux_kernel:-:*:*:*:*:*:*:*", "m3", vulnerable=False)]}]}]},
    {"id": "CVE-2024-0001", "published": "2024-01-15T00:00:00.000", "lastModified": "2024-01-20T00:00:00.000",
     "metrics": {"cvssMetricV40": [metric("4.0", 8.7, "Secondary", "cna@acme.test")],
                 "cvssMetricV31": [metric("3.1", 7.5, "Secondary", "cna@acme.test")]},
     "weaknesses": [],
     "configurations": [{"nodes": [{"cpeMatch": [
         cpe_match("cpe:2.3:a:acme:node\\:js_plugin:1.2:*:*:*:*:*:*:*", "m4"),
         cpe_match("cpe:2.3:h:acme:node\\:js_plugin:-:*:*:*:*:*:*:*", "m5"),
     ]}]}]},
    {"id": "CVE-1999-9999", "published": "1999-01-01T00:00:00.000", "lastModified": "1999-01-01T00:00:00.000",
     "metrics": {}, "weaknesses": [], "configurations": []},
]


@pytest.fixture(name="data")
def fixture_data():
    return ingest_kev_nvd.parse(KEV_CATALOG, NVD_CVES)


def test_kev_rows(data):
    log4shell = data.kev[0]
    assert log4shell["cve_id"] == "CVE-2021-44228"
    assert log4shell["date_added"] == "2021-12-10" and log4shell["due_date"] == "2021-12-24"
    assert log4shell["props"]["known_ransomware_use"] is True
    assert log4shell["props"]["kev_vendor"] == "Apache"
    assert data.kev[1]["props"]["known_ransomware_use"] is False


def test_cvss_prefers_primary_over_newer_secondary():
    cvss = ingest_kev_nvd.select_cvss(NVD_CVES[0]["metrics"])
    assert cvss == {"cvss_score": 10.0, "cvss_severity": "CRITICAL", "cvss_vector": "CVSS:3.1/AV:N",
                    "cvss_version": "3.1", "cvss_source": "nvd@nist.gov", "cvss_source_type": "Primary"}


def test_cvss_falls_back_to_secondary_newest_version():
    cvss = ingest_kev_nvd.select_cvss(NVD_CVES[1]["metrics"])
    assert (cvss["cvss_score"], cvss["cvss_version"], cvss["cvss_source"], cvss["cvss_source_type"]) == (
        8.7, "4.0", "cna@acme.test", "Secondary")


def test_cvss_v2_severity_and_absence():
    cvss = ingest_kev_nvd.select_cvss({"cvssMetricV2": [metric("2.0", 9.3, "Primary", v2=True)]})
    assert cvss["cvss_severity"] == "HIGH" and cvss["cvss_version"] == "2.0"
    assert ingest_kev_nvd.select_cvss({}) is None


def test_ssvc(data):
    assert ingest_kev_nvd.select_ssvc(NVD_CVES[0]["metrics"]) == {
        "ssvc_exploitation": "active", "ssvc_automatable": "yes", "ssvc_technical_impact": "total"}
    assert not ingest_kev_nvd.select_ssvc({})
    assert data.nvd[0]["published"] == "2021-12-10T10:15:09.143Z"


def test_only_kev_cves_are_enriched(data):
    assert [row["cve_id"] for row in data.nvd] == ["CVE-2021-44228", "CVE-2024-0001"]
    assert data.skipped["NVD record for a CVE not in KEV"] == 1
    assert data.skipped["KEV CVE without an NVD record"] == 1


def test_weaknesses_merge_kev_and_nvd_sources(data):
    assert data.weaknesses == [
        {"cve_id": "CVE-2021-44228", "cwe_id": "CWE-20", "sources": ["kev"]},
        {"cve_id": "CVE-2021-44228", "cwe_id": "CWE-502", "sources": ["security@apache.org"]},
        {"cve_id": "CVE-2021-44228", "cwe_id": "CWE-917", "sources": ["kev", "nvd@nist.gov"]},
    ]
    assert data.skipped["weakness placeholder: NVD-CWE-noinfo"] == 1


def test_split_cpe_keeps_escaped_colons():
    fields = ingest_kev_nvd.split_cpe("cpe:2.3:a:acme:node\\:js_plugin:1.2:*:*:*:*:*:*:*")
    assert fields[3:6] == ["acme", "node\\:js_plugin", "1.2"]
    assert ingest_kev_nvd.unescape(fields[4]) == "node:js_plugin"


def test_products_vendors_and_affects(data):
    assert [p["product_key"] for p in data.products] == ["acme:node\\:js_plugin", "apache:log4j"]
    assert data.products[0]["part"] == "a"  # seen as both 'a' and 'h'
    assert data.products[0]["name"] == "node:js_plugin"
    assert data.vendors == [{"vendor_key": "acme", "name": "acme"}, {"vendor_key": "apache", "name": "apache"}]
    by_id = {row["match_criteria_id"]: row for row in data.affects}
    assert set(by_id) == {"m1", "m2", "m4", "m5"}  # m2 deduplicated, m3 not vulnerable
    assert by_id["m1"]["props"] == {"criteria": "cpe:2.3:a:apache:log4j:*:*:*:*:*:*:*:*",
                                    "version_start_including": "2.0", "version_end_excluding": "2.15.0"}
    assert by_id["m2"]["props"]["version"] == "2.0"
    assert data.skipped["CPE match with vulnerable=false (platform context)"] == 1


def test_expected_counts(data):
    assert data.expected_counts() == {"CVE": 3, "CVE_with_cvss": 2, "CWE": 3, "Product": 2, "Vendor": 2,
                                      "HAS_WEAKNESS": 3, "AFFECTS": 4, "MADE_BY": 2}


def test_load_order_and_parameters(data):
    driver = FakeDriver()
    ingest_kev_nvd.load(driver, data)
    queries = [q for q, _, _ in driver.queries]
    assert queries == [ingest_kev_nvd.CVE_KEV_QUERY, ingest_kev_nvd.CVE_NVD_QUERY, ingest_kev_nvd.WEAKNESS_QUERY,
                       ingest_kev_nvd.VENDOR_QUERY, ingest_kev_nvd.PRODUCT_QUERY, ingest_kev_nvd.AFFECTS_QUERY]
    for query, params, _ in driver.queries:
        assert "CVE-2021-44228" not in query and set(params) == {"rows"}


def write_raw(tmp_path):
    raw = tmp_path / "raw"
    (raw / KEV.name).mkdir(parents=True)
    (raw / "nvd").mkdir()
    (raw / KEV.name / KEV.filename).write_text(json.dumps(KEV_CATALOG), encoding="utf-8")
    (raw / "nvd" / NVD_FILENAME).write_text(json.dumps({"cves": NVD_CVES}), encoding="utf-8")
    (raw / "manifest.json").write_text(json.dumps({"kev": {"version": "2026.10.14", "sha256": "k"},
                                                   "nvd": {"version": "2026-10-15", "sha256": "n"}}),
                                       encoding="utf-8")


def install(monkeypatch, tmp_path, driver):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)


def counting_driver(counts):
    def responder(query, _parameters):
        return [counts] if query.startswith("RETURN COUNT") else []

    return FakeDriver(responder)


def test_main_loads_records_imports_and_verifies(monkeypatch, tmp_path, data):
    write_raw(tmp_path)
    driver = counting_driver(data.expected_counts())
    install(monkeypatch, tmp_path, driver)
    assert ingest_kev_nvd.main() == 0
    metas = [params for query, params, _ in driver.queries if query.startswith("MERGE (m:ImportMeta")]
    assert metas == [{"source": "kev", "version": "2026.10.14", "file": KEV.filename, "sha256": "k"},
                     {"source": "nvd", "version": "2026-10-15", "file": NVD_FILENAME, "sha256": "n"}]


def test_main_reports_count_mismatch(monkeypatch, tmp_path, data):
    write_raw(tmp_path)
    install(monkeypatch, tmp_path, counting_driver(data.expected_counts() | {"AFFECTS": 0}))
    assert ingest_kev_nvd.main() == 1


def test_main_requires_downloads(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_kev_nvd.main() == 1


def test_main_rejects_invalid_catalog(monkeypatch, tmp_path):
    write_raw(tmp_path)
    (tmp_path / "raw" / KEV.name / KEV.filename).write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
    install(monkeypatch, tmp_path, FakeDriver())
    assert ingest_kev_nvd.main() == 1


def test_main_fails_when_neo4j_is_down(monkeypatch, tmp_path):
    write_raw(tmp_path)

    def responder(query, parameters):
        raise ServiceUnavailable("down")

    install(monkeypatch, tmp_path, FakeDriver(responder))
    assert ingest_kev_nvd.main() == 1
