"""Graph-algorithm answers: stored centrality (question 6), live group similarity (D17) and the greedy
mitigation plan (question 5)."""

import uuid
from datetime import date
from typing import Any

from neo4j import Driver, RoutingControl

from app.models.analytics import CentralTechniquesResponse, MitigationPlanResponse, SimilarGroupsResponse

# Question 6 (D15, D16): reads the properties `make analytics` wrote. Returns no row if analytics
# never ran. Sorting all ~700 techniques by a property is O(n log n) on a tiny n; communities group
# the same techniques once more, O(n).
CENTRAL_QUERY = """
MATCH (m:ImportMeta {source: 'analytics'})
RETURN m {gds_version: m.version, computed_at: toString(m.imported_at), .parameters, .community_count,
          .modularity} AS analytics,
       COLLECT {
         MATCH (t:Technique) WHERE t.used_by_groups > 0
         RETURN t {.attack_id, .name, .used_by_groups, .betweenness, .community, .community_size}
         ORDER BY CASE $by WHEN 'betweenness' THEN t.betweenness ELSE t.used_by_groups END DESC, t.attack_id
         LIMIT $limit
       } AS techniques,
       COLLECT {
         MATCH (t:Technique) WHERE t.community_size >= $min_community_size
         WITH t ORDER BY t.used_by_groups DESC, t.attack_id
         WITH t.community AS community, t.community_size AS size, collect(t.name) AS names
         ORDER BY size DESC, community
         LIMIT $community_limit
         RETURN {community: community, size: size, top_techniques: names[0..$members]}
       } AS communities
"""

# D17: index seek on attack_id, O(log n), plus the group's technique count, O(its degree).
GROUP_PROFILE_QUERY = (
    "MATCH (g:Group {attack_id: $group_id}) "
    "RETURN g {.attack_id, .name, .aliases} AS group, COUNT { (g)-[:USES]->(:Technique) } AS techniques_used"
)
# Groups and techniques only, so Group -> Software USES relationships are left out. About 50 ms.
SIMILARITY_PROJECTION = (
    "CALL gds.graph.project($graph, ['Group', 'Technique'], 'USES') "
    "YIELD graphName RETURN graphName"
)
# Filtered node similarity compares only the source group against every other group: O(groups x
# techniques per group) instead of all pairs. Jaccard = |shared techniques| / |techniques either uses|.
SIMILAR_GROUPS_QUERY = """
MATCH (g:Group {attack_id: $group_id})
CALL gds.nodeSimilarity.filtered.stream($graph, {sourceNodeFilter: [g], targetNodeFilter: 'Group',
                                                 similarityMetric: 'JACCARD', topK: $limit})
YIELD node2, similarity
WITH g, gds.util.asNode(node2) AS other, similarity
RETURN other.attack_id AS attack_id, other.name AS name, round(similarity, 4) AS jaccard,
       COUNT { (g)-[:USES]->(t:Technique)<-[:USES]-(other) } AS shared_techniques,
       COUNT { (other)-[:USES]->(:Technique) } AS techniques_used
ORDER BY jaccard DESC, attack_id
"""
DROP_PROJECTION = "CALL gds.graph.drop($graph, false) YIELD graphName RETURN graphName"

# Question 5 (D14): the weight of each reachable technique is the number of exploited CVEs (in scope)
# mapped to it, through verified bridge relationships only. Reads every bridge relationship once,
# O(|bridge|) = about 1,200, then each reached technique's mitigations.
PLAN_WEIGHTS_QUERY = """
MATCH (c:CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
WHERE $since IS NULL OR c.date_added >= date($since)
WITH t, count(DISTINCT c) AS weight
RETURN t.attack_id AS attack_id, t.name AS name, weight,
       COLLECT { MATCH (m:Mitigation)-[:MITIGATES]->(t) RETURN m {.attack_id, .name} } AS mitigations
"""
PLAN_SCOPE_QUERY = """
MATCH (c:CVE) WHERE $since IS NULL OR c.date_added >= date($since)
RETURN count(c) AS kev_cves,
       count(CASE WHEN EXISTS { (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->() } THEN 1 END) AS mapped_cves
"""

PLAN_WEIGHTING = "weight of a technique = number of exploited CVEs (in scope) CTID maps to it"
PLAN_GUARANTEE = (
    "Weighted maximum coverage is NP-hard. Greedy picks the mitigation adding the most uncovered weight; "
    "its first k picks always cover at least 1 - 1/e (about 63%) of what the best possible k mitigations could."
)


def central_techniques(driver: Driver, *, by: str = "used_by_groups", limit: int = 20, community_limit: int = 6,
                       members: int = 5, min_community_size: int = 5) -> CentralTechniquesResponse | None:
    """Return the stored centrality ranking and communities, or None if make analytics has not run."""
    records, _, _ = driver.execute_query(
        CENTRAL_QUERY,
        {"by": by, "limit": limit, "community_limit": community_limit, "members": members,
         "min_community_size": min_community_size},
        routing_=RoutingControl.READ,
    )
    if not records:
        return None
    record = records[0]
    return CentralTechniquesResponse(analytics=record["analytics"], ranked_by=by, techniques=record["techniques"],
                                     communities=record["communities"])


def similar_groups(driver: Driver, group_id: str, *, limit: int = 10) -> SimilarGroupsResponse | None:
    """Run GDS node similarity live for one group (D17), or return None if there is no such group.

    The projection gets a unique name per request and is always dropped, even if the algorithm fails.
    """
    profile, _, _ = driver.execute_query(GROUP_PROFILE_QUERY, {"group_id": group_id}, routing_=RoutingControl.READ)
    if not profile:
        return None
    graph = f"group_similarity_{uuid.uuid4().hex[:12]}"
    driver.execute_query(SIMILARITY_PROJECTION, {"graph": graph}, routing_=RoutingControl.READ)
    try:
        records, _, _ = driver.execute_query(SIMILAR_GROUPS_QUERY, {"graph": graph, "group_id": group_id,
                                                                    "limit": limit}, routing_=RoutingControl.READ)
    finally:
        driver.execute_query(DROP_PROJECTION, {"graph": graph}, routing_=RoutingControl.READ)
    return SimilarGroupsResponse(group=profile[0]["group"], techniques_used=profile[0]["techniques_used"],
                                 similar=[dict(record) for record in records])


def greedy_cover(techniques: list[dict[str, Any]],
                 max_picks: int | None = None) -> tuple[list[dict[str, Any]], set[str]]:
    """Greedy weighted maximum coverage.

    techniques: rows with attack_id, weight and mitigations ({attack_id, name}). Returns the picks in
    order, each with its gain, and the ids of the techniques left uncovered.
    """
    weight = {t["attack_id"]: t["weight"] for t in techniques}
    names: dict[str, str] = {}
    covers: dict[str, set[str]] = {}
    for technique in techniques:
        for mitigation in technique["mitigations"]:
            names[mitigation["attack_id"]] = mitigation["name"]
            covers.setdefault(mitigation["attack_id"], set()).add(technique["attack_id"])
    uncovered, picks, cumulative = set(weight), [], 0
    while covers and (max_picks is None or len(picks) < max_picks):
        # Ties go to the lower ATT&CK id so the plan is the same on every run.
        best = max(sorted(covers), key=lambda m: sum(weight[t] for t in covers[m] & uncovered))
        newly = covers.pop(best) & uncovered
        gain = sum(weight[t] for t in newly)
        if gain == 0:
            break
        uncovered -= newly
        cumulative += gain
        picks.append({"attack_id": best, "name": names[best], "gain": gain, "newly_covered_techniques": len(newly),
                      "cumulative_weight": cumulative})
    return picks, uncovered


def mitigation_plan(driver: Driver, *, since: date | None = None,
                    max_picks: int | None = None) -> MitigationPlanResponse:
    """Question 5: greedy mitigation plan over the techniques reachable from exploited CVEs (D14)."""
    params = {"since": since.isoformat() if since else None}
    techniques, _, _ = driver.execute_query(PLAN_WEIGHTS_QUERY, params, routing_=RoutingControl.READ)
    scope, _, _ = driver.execute_query(PLAN_SCOPE_QUERY, params, routing_=RoutingControl.READ)
    rows = [dict(record) for record in techniques]
    total = sum(row["weight"] for row in rows)
    pct = (lambda value: round(100 * value / total, 1)) if total else (lambda value: 0.0)
    picks, uncovered = greedy_cover(rows, max_picks)
    no_mitigation = sorted((row for row in rows if not row["mitigations"]),
                           key=lambda r: (-r["weight"], r["attack_id"]))
    uncoverable_weight = sum(row["weight"] for row in no_mitigation)
    return MitigationPlanResponse(
        scope={"since": since} | dict(scope[0]),
        weighting=PLAN_WEIGHTING,
        reachable_techniques=len(rows),
        total_weight=total,
        covered_pct=pct(total - sum(row["weight"] for row in rows if row["attack_id"] in uncovered)),
        picks=[{"rank": i, **pick, "cumulative_pct": pct(pick["cumulative_weight"])}
               for i, pick in enumerate(picks, start=1)],
        uncoverable={"technique_count": len(no_mitigation), "weight": uncoverable_weight,
                     "pct": pct(uncoverable_weight),
                     "techniques": [{"attack_id": r["attack_id"], "name": r["name"], "weight": r["weight"]}
                                    for r in no_mitigation]},
        guarantee=PLAN_GUARANTEE,
    )
