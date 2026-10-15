"""Question 3: which groups use the techniques a CVE enables (an association, never "exploits")."""

from neo4j import Driver, RoutingControl

from app.models.common import SHARED_TECHNIQUE_NOTE
from app.models.cves import CveGroupsResponse

# Only verified bridge types are followed (D12): INFERRED_MAPS_TO is never part of this pattern.
# Index seek on cve_id, O(log n), then the CVE's few mapped techniques (at most 14 in the data),
# then every group using each of them: O(sum of the techniques' USES degrees). Broad techniques such
# as T1190 are used by many groups, so groups are ranked by shared techniques and limited.
CVE_GROUPS_QUERY = """
MATCH (c:CVE {cve_id: $cve_id})
RETURN c {.cve_id, .name, .cvss_score, .cvss_source_type, .known_ransomware_use} AS cve,
       COLLECT {
         MATCH (c)-[r:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
         RETURN t {.attack_id, .name, mapping_type: type(r)} ORDER BY t.attack_id, type(r)
       } AS techniques,
       COUNT {
         MATCH (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(:Technique)<-[:USES]-(g:Group)
         RETURN DISTINCT g
       } AS group_count,
       COLLECT {
         MATCH (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)<-[:USES]-(g:Group)
         WITH g, collect(DISTINCT t.attack_id) AS shared
         ORDER BY size(shared) DESC, g.name
         LIMIT $limit
         RETURN g {.attack_id, .name, shared_techniques: shared}
       } AS groups
"""

# Model suggestions (D18), read in a separate query so they can never mix with the verified techniques
# above. The CVE's INFERRED_MAPS_TO relationships (at most 3) plus the last prediction run's status.
SUGGESTIONS_QUERY = """
MATCH (c:CVE {cve_id: $cve_id})
OPTIONAL MATCH (m:ImportMeta {source: 'predict'})
RETURN m.status AS status,
       COLLECT {
         MATCH (c)-[r:INFERRED_MAPS_TO]->(t:Technique)
         RETURN t {.attack_id, .name, confidence: r.confidence, model: r.model, model_version: r.model_version,
                   top_features: coalesce(r.top_features, []), rationale: coalesce(r.rationale, '')}
         ORDER BY r.confidence DESC, t.attack_id
       } AS suggestions
"""


def cve_groups(driver: Driver, cve_id: str, *, limit: int = 25) -> CveGroupsResponse | None:
    """Return the CVE's mapped techniques and the groups sharing them, or None if the CVE is not in KEV.

    Model suggestions are attached in their own field, labelled as model-generated.
    """
    records, _, _ = driver.execute_query(CVE_GROUPS_QUERY, {"cve_id": cve_id, "limit": limit},
                                         routing_=RoutingControl.READ)
    if not records:
        return None
    record = records[0]
    suggestions, _, _ = driver.execute_query(SUGGESTIONS_QUERY, {"cve_id": cve_id}, routing_=RoutingControl.READ)
    suggested = suggestions[0] if suggestions else {"status": None, "suggestions": []}
    return CveGroupsResponse(cve=record["cve"], note=SHARED_TECHNIQUE_NOTE, techniques=record["techniques"],
                             group_count=record["group_count"], groups=record["groups"],
                             suggested_techniques=suggested["suggestions"], suggestions_status=suggested["status"])
