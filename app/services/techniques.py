"""Question 2: which KEV CVEs are used for exploitation technique T, and which have ransomware use."""

from neo4j import Driver, RoutingControl

from app.models.techniques import TechniqueCvesResponse

# Index seek on attack_id, O(log n). With sub-techniques, also follows the technique's incoming
# SUBTECHNIQUE_OF relationships (at most a few dozen). Then reads the incoming EXPLOITS_VIA
# relationships of each, O(number of mapped CVEs). The ransomware filter is a parameter: null keeps
# every CVE, true or false keeps only matching ones.
TECHNIQUE_CVES_QUERY = """
MATCH (t:Technique {attack_id: $technique_id})
RETURN t {.attack_id, .name} AS technique,
       COLLECT {
         MATCH (x:Technique)
         WHERE x = t OR ($include_subtechniques AND (x)-[:SUBTECHNIQUE_OF]->(t))
         MATCH (c:CVE)-[r:EXPLOITS_VIA]->(x)
         WHERE $ransomware IS NULL OR c.known_ransomware_use = $ransomware
         RETURN c {.cve_id, .name, .cvss_score, .cvss_source_type, .known_ransomware_use,
                   date_added: toString(c.date_added), mapped_technique: x.attack_id, mapping_comment: r.comments}
         ORDER BY c.cvss_score DESC, c.cve_id
       } AS cves
"""


def technique_cves(driver: Driver, technique_id: str, *, ransomware: bool | None = None,
                   include_subtechniques: bool = True) -> TechniqueCvesResponse | None:
    """Return the CVEs CTID maps to the technique as exploitation, or None if there is no such technique."""
    records, _, _ = driver.execute_query(
        TECHNIQUE_CVES_QUERY,
        {"technique_id": technique_id, "ransomware": ransomware, "include_subtechniques": include_subtechniques},
        routing_=RoutingControl.READ,
    )
    if not records:
        return None
    record = records[0]
    return TechniqueCvesResponse(technique=record["technique"], include_subtechniques=include_subtechniques,
                                 cve_count=len(record["cves"]), cves=record["cves"])
