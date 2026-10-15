"""Load the CTID KEV -> ATT&CK mappings into Neo4j: the CVE <-> technique bridge.

Reads the CTID mapping file and the ATT&CK bundle fetched by scripts.download, and follows
docs/modeling_rationale.md:

- one relationship type per mapping type (D11): exploitation_technique -> EXPLOITS_VIA,
  primary_impact -> PRIMARY_IMPACT, secondary_impact -> SECONDARY_IMPACT; each carries
  source: 'ctid', attack_version, mapping_date, comments and references;
- the mappings target ATT&CK 16.1 while the graph holds v20 (D2): a technique id that v20 revoked
  is followed through its revoked-by links to the live successor, the relationship records the
  original id in remapped_from, and every remap is written to the import log; an id with no live
  successor is dropped and logged.

Run after scripts.ingest_attack and scripts.ingest_kev_nvd: both ends must already exist.
Writes use UNWIND + MERGE in batches (D13); counts are verified after loading.

Usage:
    python -m scripts.ingest_ctid
"""

import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from neo4j import Driver, RoutingControl

from app.database.batch import run_batched
from scripts.common import check_counts, read_manifest, run_with_driver, setup_logging
from scripts.download import ATTACK, CTID, DownloadError, validate_attack, validate_ctid
from scripts.ingest_attack import attack_reference, is_live

LOGGER = logging.getLogger("ingest_ctid")

MAPPING_TYPES = {
    "exploitation_technique": "EXPLOITS_VIA",
    "primary_impact": "PRIMARY_IMPACT",
    "secondary_impact": "SECONDARY_IMPACT",
}

# Both ends are found by index seek (cve_id, attack_id), then the relationship is merged: O(log n + degree)
# per row. One relationship per (CVE, mapping type, technique); relationship types cannot be parameters,
# so each type has its own query.
MAPPING_QUERIES = {
    "EXPLOITS_VIA": (
        "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) MATCH (t:Technique {attack_id: row.attack_id}) "
        "MERGE (c)-[r:EXPLOITS_VIA]->(t) SET r += row.props, r.mapping_date = date(row.mapping_date)"
    ),
    "PRIMARY_IMPACT": (
        "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) MATCH (t:Technique {attack_id: row.attack_id}) "
        "MERGE (c)-[r:PRIMARY_IMPACT]->(t) SET r += row.props, r.mapping_date = date(row.mapping_date)"
    ),
    "SECONDARY_IMPACT": (
        "UNWIND $rows AS row MATCH (c:CVE {cve_id: row.cve_id}) MATCH (t:Technique {attack_id: row.attack_id}) "
        "MERGE (c)-[r:SECONDARY_IMPACT]->(t) SET r += row.props, r.mapping_date = date(row.mapping_date)"
    ),
}
# Endpoints that must exist before the bridge is written, so a missing load fails loudly. Each id is an
# index seek, O(log n); collect() always returns exactly one row, even for an empty list.
MISSING_CVES_QUERY = (
    "UNWIND $ids AS id OPTIONAL MATCH (c:CVE {cve_id: id}) WITH id, c WHERE c IS NULL RETURN collect(id) AS missing"
)
MISSING_TECHNIQUES_QUERY = (
    "UNWIND $ids AS id OPTIONAL MATCH (t:Technique {attack_id: id}) WITH id, t WHERE t IS NULL "
    "RETURN collect(id) AS missing"
)
IMPORT_META_QUERY = (
    "MERGE (m:ImportMeta {source: 'ctid'}) "
    "SET m.version = $version, m.file = $file, m.sha256 = $sha256, m.attack_version = $attack_version, "
    "m.remap_log = $remap_log, m.imported_at = datetime()"
)
# COUNT {} on one relationship type comes from the count store, O(1); the mapped-CVE count checks
# each CVE's relationships, O(number of CVEs).
COUNT_QUERY = (
    "RETURN COUNT { ()-[:EXPLOITS_VIA]->() } AS EXPLOITS_VIA, COUNT { ()-[:PRIMARY_IMPACT]->() } AS PRIMARY_IMPACT, "
    "COUNT { ()-[:SECONDARY_IMPACT]->() } AS SECONDARY_IMPACT, "
    "COUNT { (c:CVE) WHERE EXISTS { (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->() } } AS mapped_CVE, "
    "COUNT { ()-[r:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->() WHERE r.remapped_from IS NOT NULL } AS remapped"
)


@dataclass
class CtidData:
    """Relationship rows per type, the remap log, and what was skipped."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    remap_log: list[str] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)

    def expected_counts(self) -> dict[str, int]:
        """The relationship counts the graph should hold after loading."""
        counts = {rel_type: len(self.rows.get(rel_type, [])) for rel_type in MAPPING_QUERIES}
        all_rows = [row for rows in self.rows.values() for row in rows]
        counts["mapped_CVE"] = len({row["cve_id"] for row in all_rows})
        counts["remapped"] = sum(1 for row in all_rows if "remapped_from" in row["props"])
        return counts

    def endpoint_ids(self) -> tuple[list[str], list[str]]:
        """The CVE ids and ATT&CK ids every row needs, sorted."""
        all_rows = [row for rows in self.rows.values() for row in rows]
        return sorted({r["cve_id"] for r in all_rows}), sorted({r["attack_id"] for r in all_rows})


def technique_successors(bundle: dict[str, Any]) -> tuple[set[str], dict[str, str | None]]:
    """Return the live technique ids, and for every retired technique id its live successor (or None).

    Follows revoked-by chains (A revoked by B, B revoked by C -> C). Deprecated techniques have no
    successor.
    """
    objects = bundle["objects"]
    techniques = {o["id"]: o for o in objects if o["type"] == "attack-pattern"}
    revoked_by = {o["source_ref"]: o["target_ref"] for o in objects
                  if o["type"] == "relationship" and o["relationship_type"] == "revoked-by"}
    live = {attack_reference(o)[0] for o in techniques.values() if is_live(o)}
    successors: dict[str, str | None] = {}
    for stix_id, obj in techniques.items():
        if is_live(obj):
            continue
        current, seen = stix_id, set()
        while current in revoked_by and current not in seen:
            seen.add(current)
            current = revoked_by[current]
        target = techniques.get(current)
        successor = attack_reference(target)[0] if target is not None and is_live(target) else None
        successors.setdefault(attack_reference(obj)[0], successor)
    return live, successors


def mapping_date(metadata: dict[str, Any]) -> str:
    """The KEV snapshot date the mappings were made against, as YYYY-MM-DD (CTID writes MM/DD/YYYY)."""
    return datetime.strptime(metadata["mapping_framework_version"], "%m/%d/%Y").date().isoformat()


def parse(ctid: dict[str, Any], live_techniques: set[str], successors: dict[str, str | None]) -> CtidData:
    """Turn CTID mapping objects into rows, remapping or dropping stale technique ids."""
    data = CtidData()
    attack_version = ctid["metadata"]["attack_version"]
    date = mapping_date(ctid["metadata"])
    seen: set[tuple[str, str, str]] = set()
    for mapping in ctid["mapping_objects"]:
        rel_type = MAPPING_TYPES.get(mapping["mapping_type"])
        cve_id, original = mapping["capability_id"], mapping["attack_object_id"]
        if rel_type is None:
            data.skipped[f"mapping type not in schema: {mapping['mapping_type']}"] += 1
            continue
        props: dict[str, Any] = {"source": "ctid", "attack_version": attack_version,
                                 "comments": mapping.get("comments") or "",
                                 "references": mapping.get("references") or []}
        attack_id = original
        if original not in live_techniques:
            attack_id = successors.get(original)
            if attack_id is None:
                data.remap_log.append(f"{cve_id} {rel_type} {original}: dropped, no live successor in ATT&CK v20")
                data.skipped["mapping to a technique with no live successor"] += 1
                continue
            props["remapped_from"] = original
            data.remap_log.append(f"{cve_id} {rel_type} {original} -> {attack_id}")
        if (cve_id, rel_type, attack_id) in seen:
            data.skipped["duplicate mapping after remap"] += 1
            continue
        seen.add((cve_id, rel_type, attack_id))
        data.rows.setdefault(rel_type, []).append(
            {"cve_id": cve_id, "attack_id": attack_id, "mapping_date": date, "props": props})
    return data


def missing_endpoints(driver: Driver, data: CtidData) -> tuple[list[str], list[str]]:
    """Return the CVE ids and technique ids the rows need but the graph lacks."""
    cve_ids, attack_ids = data.endpoint_ids()
    missing = []
    for query, ids in ((MISSING_CVES_QUERY, cve_ids), (MISSING_TECHNIQUES_QUERY, attack_ids)):
        records, _, _ = driver.execute_query(query, {"ids": ids}, routing_=RoutingControl.READ)
        missing.append(records[0]["missing"])
    return missing[0], missing[1]


def load(driver: Driver, data: CtidData, batch_size: int = 1000) -> None:
    """Write the bridge relationships, one query per relationship type."""
    for rel_type, query in MAPPING_QUERIES.items():
        run_batched(driver, query, data.rows.get(rel_type, []), batch_size)


def graph_counts(driver: Driver) -> dict[str, int]:
    """Return the relationship counts CTID ingestion is responsible for."""
    records, _, _ = driver.execute_query(COUNT_QUERY, routing_=RoutingControl.READ)
    return dict(records[0])


def _load_and_count(data: CtidData, meta: dict[str, Any]) -> Callable[[Driver], dict[str, int] | None]:
    def work(driver: Driver) -> dict[str, int] | None:
        missing_cves, missing_techniques = missing_endpoints(driver, data)
        if missing_cves or missing_techniques:
            LOGGER.error("run make ingest for ATT&CK and KEV first; missing CVEs %s, techniques %s",
                         missing_cves[:10], missing_techniques[:10])
            return None
        load(driver, data)
        driver.execute_query(IMPORT_META_QUERY, meta | {"remap_log": data.remap_log})
        return graph_counts(driver)

    return work


def main() -> int:
    """Load the CTID bridge into Neo4j and verify the counts. Returns a process exit code."""
    settings = setup_logging()
    ctid_path = settings.raw_dir / CTID.name / CTID.filename
    attack_path = settings.raw_dir / ATTACK.name / ATTACK.filename
    for path in (ctid_path, attack_path):
        if not path.exists():
            LOGGER.error("%s not found: run `make download` first", path)
            return 1
    ctid = json.loads(ctid_path.read_text(encoding="utf-8"))
    bundle = json.loads(attack_path.read_text(encoding="utf-8"))
    try:
        attack_version = validate_ctid(ctid)
        validate_attack(bundle)
    except DownloadError as exc:
        LOGGER.error("%s", exc)
        return 1
    data = parse(ctid, *technique_successors(bundle))
    for line in data.remap_log:
        LOGGER.info("remap: %s", line)
    for reason, count in sorted(data.skipped.items()):
        LOGGER.info("skipped %5d  %s", count, reason)

    entry = read_manifest(settings.raw_dir).get("ctid", {})
    meta = {"version": entry.get("version", attack_version), "file": CTID.filename, "sha256": entry.get("sha256"),
            "attack_version": attack_version}
    actual = run_with_driver(_load_and_count(data, meta), LOGGER)
    if actual is None or not check_counts(data.expected_counts(), actual, LOGGER):
        return 1
    LOGGER.info("CTID KEV -> ATT&CK %s bridge loaded", attack_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
