"""Compute technique centrality and communities with GDS and store them as properties (D15, D16).

Writes on every :Technique:
- used_by_groups: how many groups use it (degree; "most used");
- betweenness:    betweenness centrality on the technique co-usage graph (P2; "connectors");
- community, community_size: Louvain community on the top-k Jaccard similarity graph (P3; "used together").

Records the run, its GDS version and parameters, in :ImportMeta {source: 'analytics'}.
Run after make ingest; safe to re-run (every property is recomputed).

Usage:
    python -m scripts.analytics
"""

import json
import logging
import uuid
from typing import Any

from neo4j import Driver, RoutingControl

from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("analytics")

# Parameters of the similarity projection P3 and of Louvain, recorded with the results.
PARAMETERS: dict[str, Any] = {
    "similarity": {"metric": "JACCARD", "topK": 10, "similarityCutoff": 0.1, "degreeCutoff": 2},
    "louvain": {"relationshipWeightProperty": "jaccard", "concurrency": 1},
    "betweenness": {"graph": "technique co-usage (techniques used by a common group)", "weighted": False},
}

# Every technique gets fresh values, so a technique that lost its groups does not keep stale scores.
RESET_QUERY = (
    "MATCH (t:Technique) "
    "SET t.used_by_groups = COUNT { (:Group)-[:USES]->(t) }, t.betweenness = 0.0, "
    "t.community = null, t.community_size = null"
)

# P2: techniques linked when a common group uses both. Builds one row per (group, technique pair):
# O(sum over groups of d^2) for a group using d techniques, about 92,000 pairs here.
COOCCURRENCE_PROJECTION = """
MATCH (t1:Technique)<-[:USES]-(:Group)-[:USES]->(t2:Technique)
WHERE elementId(t1) < elementId(t2)
WITH t1, t2, count(*) AS shared
WITH gds.graph.project($graph, t1, t2, {relationshipProperties: {shared: shared}},
                       {undirectedRelationshipTypes: ['*']}) AS g
RETURN g.nodeCount AS nodes, g.relationshipCount AS relationships
"""
# Brandes' algorithm: O(n * m) on an unweighted graph, about 0.3 s here.
BETWEENNESS_WRITE = (
    "CALL gds.betweenness.write($graph, {writeProperty: 'betweenness'}) "
    "YIELD nodePropertiesWritten RETURN nodePropertiesWritten"
)

# P3: Technique -> Group (USES reversed) so techniques are the nodes compared by nodeSimilarity.
SIMILARITY_PROJECTION = (
    "CALL gds.graph.project($graph, ['Group', 'Technique'], {USES: {orientation: 'REVERSE'}}) "
    "YIELD nodeCount, relationshipCount RETURN nodeCount AS nodes, relationshipCount AS relationships"
)
SIMILARITY_MUTATE = (
    "CALL gds.nodeSimilarity.mutate($graph, {similarityMetric: $metric, topK: $topK, "
    "similarityCutoff: $similarityCutoff, degreeCutoff: $degreeCutoff, "
    "mutateRelationshipType: 'SIMILAR', mutateProperty: 'jaccard'}) "
    "YIELD relationshipsWritten RETURN relationshipsWritten"
)
# Single-threaded so the communities are the same on every run.
LOUVAIN_WRITE = (
    "CALL gds.louvain.write($graph, {nodeLabels: ['Technique'], relationshipTypes: ['SIMILAR'], "
    "relationshipWeightProperty: $relationshipWeightProperty, concurrency: $concurrency, "
    "writeProperty: 'community'}) "
    "YIELD communityCount, modularity RETURN communityCount, modularity"
)
COMMUNITY_SIZE_QUERY = (
    "MATCH (t:Technique) WHERE t.community IS NOT NULL "
    "WITH t.community AS community, collect(t) AS members "
    "FOREACH (t IN members | SET t.community_size = size(members))"
)
DROP_PROJECTION = "CALL gds.graph.drop($graph, false) YIELD graphName RETURN graphName"

IMPORT_META_QUERY = (
    "MERGE (m:ImportMeta {source: 'analytics'}) "
    "SET m.version = gds.version(), m.parameters = $parameters, m.imported_at = datetime(), "
    "m.community_count = $community_count, m.modularity = $modularity"
)
CHECK_QUERY = (
    "MATCH (t:Technique) RETURN count(t) AS techniques, "
    "count(t.used_by_groups) AS with_degree, count(t.betweenness) AS with_betweenness, "
    "count(t.community) AS with_community"
)


def _project_and_run(driver: Driver, projection: str, steps: list[tuple[str, dict[str, Any]]],
                     prefix: str) -> list[list[dict[str, Any]]]:
    """Project an in-memory graph under a unique name, run steps on it, and always drop it."""
    graph = f"{prefix}_{uuid.uuid4().hex[:12]}"
    try:
        driver.execute_query(projection, {"graph": graph})
        results = []
        for query, params in steps:
            records, _, _ = driver.execute_query(query, {"graph": graph} | params)
            results.append([dict(record) for record in records])
        return results
    finally:
        driver.execute_query(DROP_PROJECTION, {"graph": graph})


def compute(driver: Driver) -> dict[str, Any]:
    """Compute and write every analytics property. Returns a summary of the run."""
    driver.execute_query(RESET_QUERY)
    _project_and_run(driver, COOCCURRENCE_PROJECTION, [(BETWEENNESS_WRITE, {})], "analytics_cooccurrence")
    results = _project_and_run(driver, SIMILARITY_PROJECTION,
                               [(SIMILARITY_MUTATE, PARAMETERS["similarity"]), (LOUVAIN_WRITE, PARAMETERS["louvain"])],
                               "analytics_similarity")
    louvain = results[1][0]
    driver.execute_query(COMMUNITY_SIZE_QUERY)
    summary = {"community_count": louvain["communityCount"], "modularity": louvain["modularity"]}
    driver.execute_query(IMPORT_META_QUERY, {"parameters": json.dumps(PARAMETERS, sort_keys=True)} | summary)
    records, _, _ = driver.execute_query(CHECK_QUERY, routing_=RoutingControl.READ)
    return summary | dict(records[0])


def main() -> int:
    """Run the analytics and check every technique received its properties. Returns an exit code."""
    setup_logging()
    summary = run_with_driver(compute, LOGGER)
    if summary is None:
        return 1
    LOGGER.info("communities: %d (modularity %.3f)", summary["community_count"], summary["modularity"])
    missing = {key: summary["techniques"] - summary[key]
               for key in ("with_degree", "with_betweenness", "with_community")
               if summary[key] != summary["techniques"]}
    if missing:
        LOGGER.error("techniques missing analytics properties: %s", missing)
        return 1
    LOGGER.info("analytics written on %d techniques", summary["techniques"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
