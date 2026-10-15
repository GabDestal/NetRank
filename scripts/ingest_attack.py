"""Load MITRE ATT&CK Enterprise into Neo4j.

Reads the bundle fetched by scripts.download and follows docs/modeling_rationale.md:

- only objects that are neither revoked nor deprecated are loaded (D2);
- sub-techniques are :Technique:SubTechnique nodes (D3), tactics are :Tactic nodes (D4),
  software is :Software:Malware or :Software:Tool (D5), campaigns are loaded (D6);
- every relationship carries source: 'attack' and its procedure text and citations (D7);
- detection content (D6) and revoked-by links are skipped and counted.

Writes use UNWIND + MERGE on the unique key in batches (D13), so re-running updates the graph in
place. After loading, node and relationship counts in Neo4j are compared with the parsed counts.

Usage:
    python -m scripts.ingest_attack
"""

import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from neo4j import Driver, RoutingControl

from app.database.batch import run_batched
from app.database.schema import apply_schema
from scripts.common import run_with_driver, setup_logging
from scripts.download import ATTACK, DownloadError, validate_attack

LOGGER = logging.getLogger("ingest_attack")

STIX_TO_KIND = {
    "intrusion-set": "Group",
    "campaign": "Campaign",
    "malware": "Malware",
    "tool": "Tool",
    "attack-pattern": "Technique",
    "x-mitre-tactic": "Tactic",
    "course-of-action": "Mitigation",
}
# The label a relationship query matches on: malware and tools are both :Software (D5).
KIND_TO_LABEL = {kind: kind for kind in STIX_TO_KIND.values()} | {"Malware": "Software", "Tool": "Software"}

# Each query MERGEs on stix_id, which is backed by a uniqueness constraint, so finding an existing
# node is an index seek, O(log n). A batch of b rows costs O(b log n); the whole load O(N log N).
# Labels cannot be query parameters, so every query is written out in full; all values are parameters.
NODE_QUERIES = {
    "Group": (
        "UNWIND $rows AS row MERGE (n:Group {stix_id: row.stix_id}) "
        "SET n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
    "Campaign": (
        "UNWIND $rows AS row MERGE (n:Campaign {stix_id: row.stix_id}) "
        "SET n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified), "
        "n.first_seen = datetime(row.first_seen), n.last_seen = datetime(row.last_seen)"
    ),
    "Malware": (
        "UNWIND $rows AS row MERGE (n:Software {stix_id: row.stix_id}) "
        "SET n:Malware, n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
    "Tool": (
        "UNWIND $rows AS row MERGE (n:Software {stix_id: row.stix_id}) "
        "SET n:Tool, n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
    "Technique": (
        "UNWIND $rows AS row MERGE (n:Technique {stix_id: row.stix_id}) "
        "SET n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
    "Tactic": (
        "UNWIND $rows AS row MERGE (n:Tactic {stix_id: row.stix_id}) "
        "SET n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
    "Mitigation": (
        "UNWIND $rows AS row MERGE (n:Mitigation {stix_id: row.stix_id}) "
        "SET n += row.props, n.created = datetime(row.created), n.modified = datetime(row.modified)"
    ),
}
# The sub-technique label is added in a second pass over the ~700 techniques: O(number of techniques).
MARK_SUBTECHNIQUES = "MATCH (t:Technique) WHERE t.is_subtechnique SET t:SubTechnique"

# Both ends are found by index seek on stix_id, then the relationship is merged. Relationships with
# their own STIX id are merged on it, so two distinct STIX relationships never collapse into one.
# Cost per row: two index seeks plus a check of the source node's relationships, O(log n + degree).
REL_QUERIES = {
    ("uses", "Group", "Technique"): (
        "UNWIND $rows AS row MATCH (s:Group {stix_id: row.source}) MATCH (t:Technique {stix_id: row.target}) "
        "MERGE (s)-[r:USES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("uses", "Group", "Software"): (
        "UNWIND $rows AS row MATCH (s:Group {stix_id: row.source}) MATCH (t:Software {stix_id: row.target}) "
        "MERGE (s)-[r:USES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("uses", "Campaign", "Technique"): (
        "UNWIND $rows AS row MATCH (s:Campaign {stix_id: row.source}) MATCH (t:Technique {stix_id: row.target}) "
        "MERGE (s)-[r:USES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("uses", "Campaign", "Software"): (
        "UNWIND $rows AS row MATCH (s:Campaign {stix_id: row.source}) MATCH (t:Software {stix_id: row.target}) "
        "MERGE (s)-[r:USES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("uses", "Software", "Technique"): (
        "UNWIND $rows AS row MATCH (s:Software {stix_id: row.source}) MATCH (t:Technique {stix_id: row.target}) "
        "MERGE (s)-[r:USES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("mitigates", "Mitigation", "Technique"): (
        "UNWIND $rows AS row MATCH (s:Mitigation {stix_id: row.source}) MATCH (t:Technique {stix_id: row.target}) "
        "MERGE (s)-[r:MITIGATES {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("attributed-to", "Campaign", "Group"): (
        "UNWIND $rows AS row MATCH (s:Campaign {stix_id: row.source}) MATCH (t:Group {stix_id: row.target}) "
        "MERGE (s)-[r:ATTRIBUTED_TO {stix_id: row.stix_id}]->(t) SET r += row.props"
    ),
    ("subtechnique-of", "Technique", "Technique"): (
        "UNWIND $rows AS row MATCH (s:Technique {stix_id: row.source}) MATCH (t:Technique {stix_id: row.target}) "
        "MERGE (s)-[r:SUBTECHNIQUE_OF]->(t) SET r.source = 'attack'"
    ),
    ("in-tactic", "Technique", "Tactic"): (
        "UNWIND $rows AS row MATCH (s:Technique {stix_id: row.source}) MATCH (t:Tactic {stix_id: row.target}) "
        "MERGE (s)-[r:IN_TACTIC]->(t) SET r.source = 'attack'"
    ),
}

IMPORT_META_QUERY = (
    "MERGE (m:ImportMeta {source: $source}) "
    "SET m.version = $version, m.file = $file, m.sha256 = $sha256, m.imported_at = datetime()"
)

# COUNT {} on a single label or relationship type is answered from Neo4j's count store, O(1).
COUNT_QUERY = (
    "RETURN COUNT { (:Group) } AS Group, COUNT { (:Campaign) } AS Campaign, COUNT { (:Malware) } AS Malware, "
    "COUNT { (:Tool) } AS Tool, COUNT { (:Technique) } AS Technique, COUNT { (:SubTechnique) } AS SubTechnique, "
    "COUNT { (:Tactic) } AS Tactic, COUNT { (:Mitigation) } AS Mitigation, "
    "COUNT { ()-[:USES]->() } AS USES, COUNT { ()-[:MITIGATES]->() } AS MITIGATES, "
    "COUNT { ()-[:ATTRIBUTED_TO]->() } AS ATTRIBUTED_TO, COUNT { ()-[:SUBTECHNIQUE_OF]->() } AS SUBTECHNIQUE_OF, "
    "COUNT { ()-[:IN_TACTIC]->() } AS IN_TACTIC"
)

REL_TYPE_NAMES = {"uses": "USES", "mitigates": "MITIGATES", "attributed-to": "ATTRIBUTED_TO",
                  "subtechnique-of": "SUBTECHNIQUE_OF", "in-tactic": "IN_TACTIC"}


@dataclass
class AttackData:
    """Rows ready to load, keyed like NODE_QUERIES and REL_QUERIES, plus what was skipped."""

    nodes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    relationships: dict[tuple[str, str, str], list[dict[str, Any]]] = field(default_factory=dict)
    skipped: Counter = field(default_factory=Counter)

    def expected_counts(self) -> dict[str, int]:
        """The node and relationship counts the graph should hold after loading."""
        counts = {kind: len(rows) for kind, rows in self.nodes.items()}
        counts["SubTechnique"] = sum(1 for row in self.nodes.get("Technique", []) if row["props"]["is_subtechnique"])
        for (rel, _, _), rows in self.relationships.items():
            name = REL_TYPE_NAMES[rel]
            counts[name] = counts.get(name, 0) + len(rows)
        return counts


def is_live(obj: dict[str, Any]) -> bool:
    """True if the object is neither revoked nor deprecated."""
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def attack_reference(obj: dict[str, Any]) -> tuple[str, str | None]:
    """Return the object's ATT&CK id (e.g. T1059) and its attack.mitre.org URL."""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"], ref.get("url")
    raise ValueError(f"{obj['id']} has no ATT&CK id")


def citations(obj: dict[str, Any]) -> list[str]:
    """Return the object's citations as 'source name (url)' strings, skipping the ATT&CK self-reference."""
    result = []
    for ref in obj.get("external_references", []):
        if ref.get("source_name") in (None, "mitre-attack"):
            continue
        url = ref.get("url")
        result.append(f"{ref['source_name']} ({url})" if url else ref["source_name"])
    return result


def node_row(obj: dict[str, Any], tactic_order: dict[str, int]) -> dict[str, Any]:
    """Turn one live STIX object into a row for its NODE_QUERIES entry."""
    attack_id, url = attack_reference(obj)
    props: dict[str, Any] = {
        "stix_id": obj["id"],
        "attack_id": attack_id,
        "name": obj["name"],
        "description": obj.get("description", ""),
        "url": url,
    }
    kind = STIX_TO_KIND[obj["type"]]
    if kind in ("Group", "Campaign"):
        props["aliases"] = obj.get("aliases", [])
    if kind in ("Malware", "Tool"):
        props["aliases"] = obj.get("x_mitre_aliases", [])
        props["platforms"] = obj.get("x_mitre_platforms", [])
    if kind == "Technique":
        props["platforms"] = obj.get("x_mitre_platforms", [])
        props["is_subtechnique"] = bool(obj.get("x_mitre_is_subtechnique"))
    if kind == "Tactic":
        props["shortname"] = obj["x_mitre_shortname"]
        props["order"] = tactic_order.get(obj["id"])
    row = {"stix_id": obj["id"], "props": props, "created": obj["created"], "modified": obj["modified"]}
    if kind == "Campaign":
        row["first_seen"] = obj.get("first_seen")
        row["last_seen"] = obj.get("last_seen")
    return row


def _kind_of(obj: dict[str, Any] | None) -> str | None:
    return KIND_TO_LABEL.get(STIX_TO_KIND.get(obj["type"], "")) if obj else None


def _relationship_rows(objects: list[dict[str, Any]], live: dict[str, dict[str, Any]], data: AttackData) -> None:
    by_id = {obj["id"]: obj for obj in objects}
    for rel in (o for o in objects if o["type"] == "relationship"):
        source, target = by_id.get(rel["source_ref"]), by_id.get(rel["target_ref"])
        key = (rel["relationship_type"], _kind_of(source), _kind_of(target))
        if key not in REL_QUERIES:
            ends = f"{source and source['type']} -> {target and target['type']}"
            data.skipped[f"{rel['relationship_type']} ({ends})"] += 1
        elif not (is_live(rel) and rel["source_ref"] in live and rel["target_ref"] in live):
            data.skipped[f"{rel['relationship_type']}: revoked or deprecated end"] += 1
        else:
            row = {"source": rel["source_ref"], "target": rel["target_ref"], "stix_id": rel["id"],
                   "props": {"source": "attack", "stix_id": rel["id"], "description": rel.get("description", ""),
                             "references": citations(rel)}}
            data.relationships.setdefault(key, []).append(row)


def parse_bundle(bundle: dict[str, Any]) -> AttackData:
    """Turn an ATT&CK STIX bundle into rows for NODE_QUERIES and REL_QUERIES."""
    objects = bundle["objects"]
    data = AttackData()
    matrix = next((o for o in objects if o["type"] == "x-mitre-matrix" and is_live(o)), {"tactic_refs": []})
    tactic_order = {stix_id: i for i, stix_id in enumerate(matrix["tactic_refs"], start=1)}

    live = {o["id"]: o for o in objects if o["type"] in STIX_TO_KIND and is_live(o)}
    for obj in objects:
        if obj["type"] in STIX_TO_KIND and obj["id"] not in live:
            data.skipped[f"{obj['type']}: revoked or deprecated"] += 1
    for obj in live.values():
        data.nodes.setdefault(STIX_TO_KIND[obj["type"]], []).append(node_row(obj, tactic_order))

    _relationship_rows(objects, live, data)

    tactic_by_shortname = {o["x_mitre_shortname"]: o["id"] for o in live.values() if o["type"] == "x-mitre-tactic"}
    for obj in (o for o in live.values() if o["type"] == "attack-pattern"):
        for phase in obj.get("kill_chain_phases", []):
            tactic = tactic_by_shortname.get(phase["phase_name"])
            if phase["kill_chain_name"] != "mitre-attack" or tactic is None:
                data.skipped[f"kill chain phase without tactic: {phase['phase_name']}"] += 1
                continue
            data.relationships.setdefault(("in-tactic", "Technique", "Tactic"), []).append(
                {"source": obj["id"], "target": tactic})
    return data


def load(driver: Driver, data: AttackData, batch_size: int = 1000) -> None:
    """Write nodes, then sub-technique labels, then relationships (which need both ends to exist)."""
    for kind, query in NODE_QUERIES.items():
        run_batched(driver, query, data.nodes.get(kind, []), batch_size)
    driver.execute_query(MARK_SUBTECHNIQUES)
    for key, query in REL_QUERIES.items():
        run_batched(driver, query, data.relationships.get(key, []), batch_size)


def graph_counts(driver: Driver) -> dict[str, int]:
    """Return the node and relationship counts ATT&CK ingestion is responsible for."""
    records, _, _ = driver.execute_query(COUNT_QUERY, routing_=RoutingControl.READ)
    return dict(records[0])


def record_import(driver: Driver, manifest_entry: dict[str, Any]) -> None:
    """Create or update the :ImportMeta node for ATT&CK from its download manifest entry."""
    driver.execute_query(IMPORT_META_QUERY, {
        "source": "attack",
        "version": manifest_entry.get("version"),
        "file": manifest_entry.get("file", ATTACK.filename),
        "sha256": manifest_entry.get("sha256"),
    })


def _load_and_count(data: AttackData, manifest_entry: dict[str, Any]) -> Callable[[Driver], dict[str, int]]:
    def work(driver: Driver) -> dict[str, int]:
        apply_schema(driver)
        load(driver, data)
        record_import(driver, manifest_entry)
        return graph_counts(driver)

    return work


def main() -> int:
    """Load ATT&CK into Neo4j and verify the counts. Returns a process exit code."""
    settings = setup_logging()
    path = settings.raw_dir / ATTACK.name / ATTACK.filename
    if not path.exists():
        LOGGER.error("%s not found: run `make download` first", path)
        return 1
    bundle = json.loads(path.read_text(encoding="utf-8"))
    try:
        version = validate_attack(bundle)
    except DownloadError as exc:
        LOGGER.error("%s", exc)
        return 1
    data = parse_bundle(bundle)
    for reason, count in sorted(data.skipped.items()):
        LOGGER.info("skipped %5d  %s", count, reason)

    manifest_path = settings.raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    actual = run_with_driver(_load_and_count(data, manifest.get("attack", {"version": version})), LOGGER)
    if actual is None:
        return 1

    expected = data.expected_counts()
    for name, count in expected.items():
        LOGGER.info("%-16s %6d", name, actual.get(name, 0))
    mismatches = {name: (count, actual.get(name)) for name, count in expected.items() if actual.get(name) != count}
    if mismatches:
        LOGGER.error("count mismatch (expected, in graph): %s", mismatches)
        return 1
    LOGGER.info("ATT&CK %s loaded", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
