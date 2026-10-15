"""Load the CISA KEV catalog and its NVD records into Neo4j.

Reads the files fetched by scripts.download and follows docs/modeling_rationale.md:

- one :CVE per KEV entry, with KEV properties, then NVD properties: dates, the CVSS score chosen
  by the D8 rule (with its source), and the CISA SSVC assessment;
- :CWE nodes from the KEV and NVD weakness lists merged, each HAS_WEAKNESS recording which lists
  named it (D9); NVD placeholders (NVD-CWE-noinfo, NVD-CWE-Other) are not CWEs and are skipped;
- :Product and :Vendor nodes at CPE vendor:product level, with one AFFECTS relationship per
  vulnerable NVD CPE match carrying its version range; vulnerable=false matches are skipped (D10).

Writes use UNWIND + MERGE in batches (D13); counts are verified after loading.

Usage:
    python -m scripts.ingest_kev_nvd
"""

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from neo4j import Driver, RoutingControl

from app.database.batch import run_batched
from app.database.schema import apply_schema
from scripts.common import check_counts, read_manifest, record_import, run_with_driver, setup_logging
from scripts.download import KEV, NVD_FILENAME, DownloadError, validate_kev

LOGGER = logging.getLogger("ingest_kev_nvd")

# D8 (with its amendment): NVD's Primary metric first, then Secondary; within each, newest CVSS version.
CVSS_KEYS = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2")
CVSS_SOURCE_TYPES = ("Primary", "Secondary")

# Every query finds its nodes through a uniqueness constraint's index (cve_id, cwe_id, product_key,
# vendor_key), so each row costs O(log n) to locate plus, for relationships, O(degree) for MERGE to
# check the existing relationships between the two nodes.
CVE_KEV_QUERY = (
    "UNWIND $rows AS row MERGE (c:CVE {cve_id: row.cve_id}) "
    "SET c += row.props, c.date_added = date(row.date_added), c.due_date = date(row.due_date)"
)
# MATCH, not MERGE: NVD only enriches CVEs that KEV listed.
CVE_NVD_QUERY = (
    "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) "
    "SET c += row.props, c.published = datetime(row.published), c.last_modified = datetime(row.last_modified)"
)
WEAKNESS_QUERY = (
    "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) MERGE (w:CWE {cwe_id: row.cwe_id}) "
    "MERGE (c)-[r:HAS_WEAKNESS]->(w) SET r.sources = row.sources"
)
VENDOR_QUERY = "UNWIND $rows AS row MERGE (v:Vendor {vendor_key: row.vendor_key}) SET v.name = row.name"
PRODUCT_QUERY = (
    "UNWIND $rows AS row MERGE (p:Product {product_key: row.product_key}) SET p.name = row.name, p.part = row.part "
    "WITH p, row MATCH (v:Vendor {vendor_key: row.vendor_key}) MERGE (p)-[:MADE_BY]->(v)"
)
# One AFFECTS per NVD CPE match, merged on NVD's matchCriteriaId so a re-run never duplicates it.
AFFECTS_QUERY = (
    "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) MATCH (p:Product {product_key: row.product_key}) "
    "MERGE (c)-[r:AFFECTS {match_criteria_id: row.match_criteria_id}]->(p) SET r += row.props"
)
# COUNT {} on one label or relationship type comes from the count store, O(1). The cvss_score
# filter reads the range index on :CVE(cvss_score) instead of every CVE.
COUNT_QUERY = (
    "RETURN COUNT { (:CVE) } AS CVE, COUNT { (c:CVE) WHERE c.cvss_score IS NOT NULL } AS CVE_with_cvss, "
    "COUNT { (:CWE) } AS CWE, COUNT { (:Product) } AS Product, COUNT { (:Vendor) } AS Vendor, "
    "COUNT { ()-[:HAS_WEAKNESS]->() } AS HAS_WEAKNESS, COUNT { ()-[:AFFECTS]->() } AS AFFECTS, "
    "COUNT { ()-[:MADE_BY]->() } AS MADE_BY"
)

VERSION_RANGE_FIELDS = {
    "versionStartIncluding": "version_start_including",
    "versionStartExcluding": "version_start_excluding",
    "versionEndIncluding": "version_end_including",
    "versionEndExcluding": "version_end_excluding",
}


@dataclass
class KevNvdData:
    """Rows ready to load, plus what was skipped and why."""

    kev: list[dict[str, Any]] = field(default_factory=list)
    nvd: list[dict[str, Any]] = field(default_factory=list)
    weaknesses: list[dict[str, Any]] = field(default_factory=list)
    vendors: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    affects: list[dict[str, Any]] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)

    def expected_counts(self) -> dict[str, int]:
        """The node and relationship counts the graph should hold after loading."""
        return {
            "CVE": len(self.kev),
            "CVE_with_cvss": sum(1 for row in self.nvd if row["props"].get("cvss_score") is not None),
            "CWE": len({row["cwe_id"] for row in self.weaknesses}),
            "Product": len(self.products),
            "Vendor": len(self.vendors),
            "HAS_WEAKNESS": len(self.weaknesses),
            "AFFECTS": len(self.affects),
            "MADE_BY": len(self.products),
        }


def kev_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Turn one KEV catalog entry into a row for CVE_KEV_QUERY."""
    return {
        "cve_id": entry["cveID"],
        "date_added": entry["dateAdded"],
        "due_date": entry.get("dueDate"),
        "props": {
            "name": entry.get("vulnerabilityName"),
            "short_description": entry.get("shortDescription"),
            "required_action": entry.get("requiredAction"),
            "known_ransomware_use": entry.get("knownRansomwareCampaignUse") == "Known",
            "kev_vendor": entry.get("vendorProject"),
            "kev_product": entry.get("product"),
        },
    }


def select_cvss(metrics: dict[str, Any]) -> dict[str, Any] | None:
    """Pick one CVSS metric by the D8 rule and return it as CVE properties, or None if there is none."""
    for source_type in CVSS_SOURCE_TYPES:
        for key in CVSS_KEYS:
            metric = next((m for m in metrics.get(key, []) if m.get("type") == source_type), None)
            if metric:
                data = metric["cvssData"]
                return {
                    "cvss_score": data["baseScore"],
                    # CVSS v2 keeps its severity next to cvssData rather than inside it.
                    "cvss_severity": data.get("baseSeverity") or metric.get("baseSeverity"),
                    "cvss_vector": data.get("vectorString"),
                    "cvss_version": data.get("version"),
                    "cvss_source": metric.get("source"),
                    "cvss_source_type": source_type,
                }
    return None


def select_ssvc(metrics: dict[str, Any]) -> dict[str, Any]:
    """Return the CISA SSVC decision points as CVE properties ({} if there is no assessment)."""
    for key, values in metrics.items():
        if key.startswith("ssvc") and values:
            options = {k: v for option in values[0]["ssvcData"].get("options", []) for k, v in option.items()}
            return {
                "ssvc_exploitation": options.get("exploitation"),
                "ssvc_automatable": options.get("automatable"),
                "ssvc_technical_impact": options.get("technicalImpact"),
            }
    return {}


def nvd_row(cve: dict[str, Any]) -> dict[str, Any]:
    """Turn one NVD CVE record into a row for CVE_NVD_QUERY."""
    metrics = cve.get("metrics", {})
    props = (select_cvss(metrics) or {}) | select_ssvc(metrics)
    # NVD timestamps are UTC without a zone designator.
    return {"cve_id": cve["id"], "published": cve["published"] + "Z", "last_modified": cve["lastModified"] + "Z",
            "props": props}


def split_cpe(criteria: str) -> list[str]:
    """Split a CPE 2.3 string on its ':' separators, keeping backslash-escaped colons inside fields."""
    fields, current, escaped = [], [], False
    for char in criteria:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def unescape(value: str) -> str:
    """Drop CPE backslash escapes for display (e.g. 'node\\.js' -> 'node.js')."""
    return value.replace("\\", "")


def _weakness_rows(kev_entries: list[dict[str, Any]], nvd_cves: list[dict[str, Any]],
                   kev_ids: set[str], data: KevNvdData) -> None:
    sources: dict[tuple[str, str], set[str]] = {}
    for entry in kev_entries:
        for cwe in entry.get("cwes", []):
            sources.setdefault((entry["cveID"], cwe), set()).add("kev")
    for cve in nvd_cves:
        if cve["id"] not in kev_ids:
            continue
        for weakness in cve.get("weaknesses", []):
            for description in weakness["description"]:
                value = description["value"]
                if not value.startswith("CWE-"):
                    data.skipped[f"weakness placeholder: {value}"] += 1
                    continue
                sources.setdefault((cve["id"], value), set()).add(weakness["source"])
    data.weaknesses = [{"cve_id": cve_id, "cwe_id": cwe_id, "sources": sorted(found)}
                       for (cve_id, cwe_id), found in sorted(sources.items())]


def _vulnerable_matches(cve: dict[str, Any], data: KevNvdData) -> Iterator[dict[str, Any]]:
    """Yield the CVE's CPE matches that are themselves vulnerable, counting the others as skipped."""
    for config in cve.get("configurations", []):
        for node in config["nodes"]:
            for match in node["cpeMatch"]:
                if match["vulnerable"]:
                    yield match
                else:
                    data.skipped["CPE match with vulnerable=false (platform context)"] += 1


def affects_props(match: dict[str, Any], version: str) -> dict[str, Any]:
    """Properties of one AFFECTS relationship: the CPE string, exact version if any, and version range."""
    props: dict[str, Any] = {"criteria": match["criteria"]}
    if version not in ("*", "-"):
        props["version"] = unescape(version)
    return props | {name: match[nvd_name] for nvd_name, name in VERSION_RANGE_FIELDS.items() if nvd_name in match}


def _cpe_rows(nvd_cves: list[dict[str, Any]], kev_ids: set[str], data: KevNvdData) -> None:
    products: dict[str, dict[str, Any]] = {}
    affects: dict[tuple[str, str], dict[str, Any]] = {}
    for cve in (c for c in nvd_cves if c["id"] in kev_ids):
        for match in _vulnerable_matches(cve, data):
            _, _, part, vendor, product, version, *_ = split_cpe(match["criteria"])
            key = f"{vendor}:{product}"
            products.setdefault(key, {"product_key": key, "vendor_key": vendor, "name": unescape(product),
                                      "parts": set()})["parts"].add(part)
            affects[(cve["id"], match["matchCriteriaId"])] = {
                "cve_id": cve["id"], "product_key": key, "match_criteria_id": match["matchCriteriaId"],
                "props": affects_props(match, version)}
    # A handful of vendor:product pairs appear under two CPE parts; keep the first alphabetically (a < h < o).
    data.products = [{**{k: v for k, v in p.items() if k != "parts"}, "part": min(p["parts"])}
                     for p in sorted(products.values(), key=lambda p: p["product_key"])]
    data.vendors = [{"vendor_key": v, "name": unescape(v)} for v in sorted({p["vendor_key"] for p in data.products})]
    data.affects = list(affects.values())


def parse(kev_catalog: dict[str, Any], nvd_cves: list[dict[str, Any]]) -> KevNvdData:
    """Turn the KEV catalog and its NVD records into rows for the queries above."""
    data = KevNvdData()
    entries = kev_catalog["vulnerabilities"]
    kev_ids = {entry["cveID"] for entry in entries}
    data.kev = [kev_row(entry) for entry in entries]
    data.nvd = [nvd_row(cve) for cve in nvd_cves if cve["id"] in kev_ids]
    extra = sum(1 for cve in nvd_cves if cve["id"] not in kev_ids)
    missing = len(kev_ids - {row["cve_id"] for row in data.nvd})
    for reason, count in (("NVD record for a CVE not in KEV", extra), ("KEV CVE without an NVD record", missing)):
        if count:
            data.skipped[reason] = count
    _weakness_rows(entries, nvd_cves, kev_ids, data)
    _cpe_rows(nvd_cves, kev_ids, data)
    return data


def load(driver: Driver, data: KevNvdData, batch_size: int = 1000) -> None:
    """Write CVEs, then their NVD details and weaknesses, then vendors, products and AFFECTS."""
    run_batched(driver, CVE_KEV_QUERY, data.kev, batch_size)
    run_batched(driver, CVE_NVD_QUERY, data.nvd, batch_size)
    run_batched(driver, WEAKNESS_QUERY, data.weaknesses, batch_size)
    run_batched(driver, VENDOR_QUERY, data.vendors, batch_size)
    run_batched(driver, PRODUCT_QUERY, data.products, batch_size)
    run_batched(driver, AFFECTS_QUERY, data.affects, batch_size)


def graph_counts(driver: Driver) -> dict[str, int]:
    """Return the node and relationship counts KEV/NVD ingestion is responsible for."""
    records, _, _ = driver.execute_query(COUNT_QUERY, routing_=RoutingControl.READ)
    return dict(records[0])


def _load_and_count(data: KevNvdData, manifest: dict[str, Any]) -> Callable[[Driver], dict[str, int]]:
    def work(driver: Driver) -> dict[str, int]:
        apply_schema(driver)
        load(driver, data)
        record_import(driver, "kev", {"file": KEV.filename} | manifest.get("kev", {}))
        record_import(driver, "nvd", {"file": NVD_FILENAME} | manifest.get("nvd", {}))
        return graph_counts(driver)

    return work


def main() -> int:
    """Load KEV and NVD into Neo4j and verify the counts. Returns a process exit code."""
    settings = setup_logging()
    kev_path = settings.raw_dir / KEV.name / KEV.filename
    nvd_path = settings.raw_dir / "nvd" / NVD_FILENAME
    for path in (kev_path, nvd_path):
        if not path.exists():
            LOGGER.error("%s not found: run `make download` first", path)
            return 1
    catalog = json.loads(kev_path.read_text(encoding="utf-8"))
    try:
        version = validate_kev(catalog)
    except DownloadError as exc:
        LOGGER.error("%s", exc)
        return 1
    data = parse(catalog, json.loads(nvd_path.read_text(encoding="utf-8"))["cves"])
    for reason, count in sorted(data.skipped.items()):
        LOGGER.info("skipped %5d  %s", count, reason)

    actual = run_with_driver(_load_and_count(data, read_manifest(settings.raw_dir)), LOGGER)
    if actual is None or not check_counts(data.expected_counts(), actual, LOGGER):
        return 1
    LOGGER.info("KEV %s and its NVD records loaded", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
