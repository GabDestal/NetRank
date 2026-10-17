"""How is a group connected to a product? A bounded, filtered shortestPath (D20)."""

from typing import Any

from neo4j import Driver, RoutingControl

from app.models.paths import ConnectionResponse, PathHop, PathNode

# Hard search bound. Cypher only accepts a literal here, and the caller's max_hops is checked on the
# result instead of inside the query: a length(path) predicate makes Neo4j fall back to an exhaustive
# search (over 20 s when no path exists), while this form stays a breadth-first ShortestPath (D20).
SEARCH_HOPS = 8
BRIDGE_TYPES = ("EXPLOITS_VIA", "PRIMARY_IMPACT", "SECONDARY_IMPACT")
MAPPING_WORDS = {"EXPLOITS_VIA": "exploitation", "PRIMARY_IMPACT": "primary impact",
                 "SECONDARY_IMPACT": "secondary impact"}

# Two index seeks, O(log n), then a breadth-first search from both ends over verified relationship types
# only (no INFERRED_MAPS_TO), up to 8 hops. Every filter is on single nodes or relationships, so Neo4j
# applies it while expanding: no other group, campaign or product in the middle; software must be the
# group's own; and a CVE can only lead to a technique if it affects this product, so the path holds one CVE.
# Cost grows with the frontier, roughly (average degree)^(hops/2) from each side; measured on 300 random
# pairs: median 4 ms, worst 769 ms.
CONNECTION_QUERY = """
OPTIONAL MATCH (g:Group {attack_id: $group_id})
OPTIONAL MATCH (p:Product {product_key: $product_key})
OPTIONAL MATCH path = shortestPath(
  (g)-[:USES|SUBTECHNIQUE_OF|EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT|AFFECTS*..8]-(p))
WHERE all(n IN nodes(path) WHERE n = g OR n = p OR NOT (n:Group OR n:Campaign OR n:Product))
  AND all(r IN relationships(path) WHERE
        (type(r) <> 'USES' OR startNode(r) = g OR EXISTS { (g)-[:USES]->(x) WHERE x = startNode(r) })
    AND (NOT type(r) IN $bridge_types OR EXISTS { (x)-[:AFFECTS]->(p) WHERE x = startNode(r) }))
RETURN g {.attack_id, .name} AS group, p {.product_key, .name} AS product,
       [n IN nodes(path) | {labels: labels(n), id: coalesce(n.attack_id, n.cve_id, n.product_key), name: n.name}]
         AS nodes,
       [r IN relationships(path) | {type: type(r),
                                    start: coalesce(startNode(r).attack_id, startNode(r).cve_id,
                                                    startNode(r).product_key)}] AS relationships
"""


class PathNotFound(LookupError):
    """The group or product does not exist, or no path is short enough. The message says which."""


def node_kind(labels: list[str]) -> str:
    """Map a node's labels to the kind shown in the response."""
    for kind in ("Group", "Software", "Technique", "CVE", "Product"):
        if kind in labels:
            return kind
    raise ValueError(f"unexpected node on a connection path: {labels}")


def label(node: PathNode) -> str:
    """'APT29 (G0016)', or just the id when the node has no name."""
    return f"{node.name} ({node.id})" if node.name and node.name != node.id else node.id


def describe_hop(before: PathNode, after: PathNode, hop: PathHop) -> str:
    """One step of the path in plain words, oriented the way the relationship points."""
    source, target = (before, after) if hop.direction == "forward" else (after, before)
    if hop.type == "USES":
        return f"{label(source)} uses {label(target)}"
    if hop.type == "SUBTECHNIQUE_OF":
        return f"{label(source)} is a sub-technique of {label(target)}"
    if hop.type == "AFFECTS":
        return f"{label(source)} affects {label(target)}"
    return f"{label(source)} is mapped to {label(target)} ({MAPPING_WORDS[hop.type]})"


def read_path(nodes: list[PathNode], hops: list[PathHop]) -> str:
    """The plain-language reading: one summary sentence, then each step."""
    cve_index = next(i for i, n in enumerate(nodes) if n.kind == "CVE")
    group, technique, cve, product = nodes[0], nodes[cve_index - 1], nodes[cve_index], nodes[-1]
    summary = f"{label(group)} shares technique {label(technique)} with {label(cve)} affecting {label(product)}"
    if cve_index > 2:
        summary += f", reached through {', '.join(label(n) for n in nodes[1:cve_index - 1])}"
    steps = "; ".join(describe_hop(nodes[i], nodes[i + 1], hop) for i, hop in enumerate(hops))
    return f"{summary}. Path: {steps}."


def to_response(record: dict[str, Any], max_hops: int) -> ConnectionResponse:
    """Build the response from the query's record, which must hold a path."""
    nodes = [PathNode(kind=node_kind(n["labels"]), id=n["id"], name=n["name"]) for n in record["nodes"]]
    hops = [PathHop(type=r["type"], direction="forward" if r["start"] == nodes[i].id else "backward")
            for i, r in enumerate(record["relationships"])]
    return ConnectionResponse(group=nodes[0], product=nodes[-1], max_hops=max_hops, hops=len(hops), nodes=nodes,
                              relationships=hops, reading=read_path(nodes, hops))


def connection_path(driver: Driver, group_id: str, product_key: str, *, max_hops: int = 6) -> ConnectionResponse:
    """Return the shortest verified path from the group to the product, or raise PathNotFound."""
    records, _, _ = driver.execute_query(
        CONNECTION_QUERY, {"group_id": group_id, "product_key": product_key, "bridge_types": list(BRIDGE_TYPES)},
        routing_=RoutingControl.READ)
    record = records[0] if records else {"group": None, "product": None, "nodes": None}
    if record["group"] is None:
        raise PathNotFound(f"Group {group_id} not found")
    if record["product"] is None:
        raise PathNotFound(f"Product {product_key} not found; use GET /products?search= to find its key")
    if record["nodes"] is None:
        raise PathNotFound(f"No verified path from {group_id} to {product_key} within {SEARCH_HOPS} hops "
                           "(group, its software, technique, one CVE affecting the product)")
    hops = len(record["relationships"])
    if hops > max_hops:
        raise PathNotFound(f"No path from {group_id} to {product_key} within {max_hops} hops; "
                           f"the shortest verified path has {hops}")
    return to_response(record, max_hops)
