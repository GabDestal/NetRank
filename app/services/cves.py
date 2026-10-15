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


def cve_groups(driver: Driver, cve_id: str, *, limit: int = 25) -> CveGroupsResponse | None:
    """Return the CVE's mapped techniques and the groups sharing them, or None if the CVE is not in KEV."""
    records, _, _ = driver.execute_query(CVE_GROUPS_QUERY, {"cve_id": cve_id, "limit": limit},
                                         routing_=RoutingControl.READ)
    if not records:
        return None
    record = records[0]
    return CveGroupsResponse(cve=record["cve"], note=SHARED_TECHNIQUE_NOTE, techniques=record["techniques"],
                             group_count=record["group_count"], groups=record["groups"])
