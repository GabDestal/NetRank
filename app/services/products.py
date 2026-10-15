"""Questions 4 and 7: the most exploited vendors and products, and one product's full exposure."""

from neo4j import Driver, RoutingControl

from app.models.common import SHARED_TECHNIQUE_NOTE
from app.models.products import (ExposureResponse, ProductRankingResponse, ProductSearchResponse,
                                 VendorRankingResponse)

# Question 4, by vendor. Reads every AFFECTS relationship once to group CVEs by vendor:
# O(|AFFECTS|), about 31,000. Only the top $limit vendors then get their weaknesses counted,
# O(their CVEs x CWEs per CVE).
TOP_VENDORS_QUERY = """
MATCH (v:Vendor)<-[:MADE_BY]-(:Product)<-[:AFFECTS]-(c:CVE)
WITH v, collect(DISTINCT c) AS cves
ORDER BY size(cves) DESC, v.vendor_key
LIMIT $limit
RETURN v.vendor_key AS vendor_key, v.name AS name, size(cves) AS exploited_cves,
       size([c IN cves WHERE c.known_ransomware_use]) AS ransomware_cves,
       COLLECT {
         UNWIND cves AS c
         MATCH (c)-[:HAS_WEAKNESS]->(w:CWE)
         WITH w, count(DISTINCT c) AS n
         ORDER BY n DESC, w.cwe_id
         LIMIT $cwe_limit
         RETURN {cwe_id: w.cwe_id, cves: n}
       } AS top_weaknesses
"""

# Question 4, by product: the same shape one level down. Also O(|AFFECTS|).
TOP_PRODUCTS_QUERY = """
MATCH (p:Product)<-[:AFFECTS]-(c:CVE)
WITH p, collect(DISTINCT c) AS cves
ORDER BY size(cves) DESC, p.product_key
LIMIT $limit
RETURN p.product_key AS product_key, p.name AS name,
       COLLECT { MATCH (p)-[:MADE_BY]->(v:Vendor) RETURN v.name }[0] AS vendor,
       size(cves) AS exploited_cves,
       size([c IN cves WHERE c.known_ransomware_use]) AS ransomware_cves,
       COLLECT {
         UNWIND cves AS c
         MATCH (c)-[:HAS_WEAKNESS]->(w:CWE)
         WITH w, count(DISTINCT c) AS n
         ORDER BY n DESC, w.cwe_id
         LIMIT $cwe_limit
         RETURN {cwe_id: w.cwe_id, cves: n}
       } AS top_weaknesses
"""

# Finds product keys by substring. CONTAINS cannot use the range index on product_key, so this
# scans all ~3,600 products, O(n); a text index would make it O(log n) if search becomes hot.
PRODUCT_SEARCH_QUERY = """
MATCH (p:Product)
WHERE p.product_key CONTAINS $term OR toLower(p.name) CONTAINS $term
WITH p, COUNT { MATCH (p)<-[:AFFECTS]-(c:CVE) RETURN DISTINCT c } AS exploited_cves
ORDER BY exploited_cves DESC, p.product_key
LIMIT $limit
RETURN p.product_key AS product_key, p.name AS name,
       COLLECT { MATCH (p)-[:MADE_BY]->(v:Vendor) RETURN v.name }[0] AS vendor, exploited_cves
"""

# Question 7. Index seek on product_key, O(log n); then the product's CVEs, O(its AFFECTS degree);
# their mapped techniques, O(CVEs x mappings per CVE); and finally the groups and mitigations of
# those techniques, O(techniques x their USES/MITIGATES degrees). Groups are linked only through
# verified bridge relationships (D12), and both rankings are limited.
EXPOSURE_QUERY = """
MATCH (p:Product {product_key: $product_key})
WITH p, COLLECT { MATCH (p)<-[:AFFECTS]-(c:CVE) RETURN DISTINCT c } AS cves
WITH p, cves,
     COLLECT { UNWIND cves AS c
               MATCH (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
               RETURN DISTINCT t } AS techniques
RETURN p {.product_key, .name, .part, vendor: COLLECT { MATCH (p)-[:MADE_BY]->(v:Vendor) RETURN v.name }[0]}
         AS product,
       [c IN cves | c {.cve_id, .name, .cvss_score, .cvss_source_type, .known_ransomware_use,
                       mapped_to_attack: EXISTS { (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->() }}]
         AS cves,
       COLLECT { UNWIND cves AS c
                 MATCH (c)-[r:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
                 WITH t, count(DISTINCT c) AS via, collect(DISTINCT type(r)) AS types
                 ORDER BY via DESC, t.attack_id
                 RETURN t {.attack_id, .name, via_cves: via, mapping_types: types} } AS techniques,
       COLLECT { UNWIND techniques AS t
                 MATCH (t)<-[:USES]-(g:Group)
                 WITH g, count(DISTINCT t) AS shared
                 ORDER BY shared DESC, g.name
                 LIMIT $limit
                 RETURN g {.attack_id, .name, shared_techniques: shared} } AS groups,
       COLLECT { UNWIND techniques AS t
                 MATCH (m:Mitigation)-[:MITIGATES]->(t)
                 WITH m, count(DISTINCT t) AS covers
                 ORDER BY covers DESC, m.attack_id
                 LIMIT $limit
                 RETURN m {.attack_id, .name, covers_techniques: covers} } AS mitigations
"""


def top_vendors(driver: Driver, *, limit: int = 10, cwe_limit: int = 3) -> VendorRankingResponse:
    """Return the vendors with the most actively exploited CVEs, each with its top weaknesses."""
    records, _, _ = driver.execute_query(TOP_VENDORS_QUERY, {"limit": limit, "cwe_limit": cwe_limit},
                                         routing_=RoutingControl.READ)
    return VendorRankingResponse(vendors=[dict(record) for record in records])


def top_products(driver: Driver, *, limit: int = 10, cwe_limit: int = 3) -> ProductRankingResponse:
    """Return the products with the most actively exploited CVEs, each with its top weaknesses."""
    records, _, _ = driver.execute_query(TOP_PRODUCTS_QUERY, {"limit": limit, "cwe_limit": cwe_limit},
                                         routing_=RoutingControl.READ)
    return ProductRankingResponse(products=[dict(record) for record in records])


def search_products(driver: Driver, term: str, *, limit: int = 20) -> ProductSearchResponse:
    """Return products whose key or name contains term (case-insensitive), most exploited first."""
    records, _, _ = driver.execute_query(PRODUCT_SEARCH_QUERY, {"term": term.lower(), "limit": limit},
                                         routing_=RoutingControl.READ)
    return ProductSearchResponse(products=[dict(record) for record in records])


def product_exposure(driver: Driver, product_key: str, *, limit: int = 10) -> ExposureResponse | None:
    """Return question 7's answer for one product, or None if there is no such product."""
    records, _, _ = driver.execute_query(EXPOSURE_QUERY, {"product_key": product_key, "limit": limit},
                                         routing_=RoutingControl.READ)
    if not records:
        return None
    record = records[0]
    cves = sorted(record["cves"], key=lambda c: (-(c["cvss_score"] or 0), c["cve_id"]))
    return ExposureResponse(
        product=record["product"],
        cve_count=len(cves),
        mapped_cve_count=sum(1 for c in cves if c["mapped_to_attack"]),
        cves=cves,
        technique_count=len(record["techniques"]),
        techniques=record["techniques"],
        note=SHARED_TECHNIQUE_NOTE,
        groups=record["groups"],
        mitigations=record["mitigations"],
    )
