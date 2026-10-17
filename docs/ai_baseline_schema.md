AI baseline schema, saved unedited on 2026-10-17. It was generated in a chat with no project context, from the prompt: "Design a Neo4j graph schema for a Cyber Threat Intelligence application that links MITRE ATT&CK, CISA KEV and NVD CVE data, so users can ask which threat groups could exploit their products and which mitigations reduce the most risk. List node labels, relationship types with direction, and key properties." Compared with our schema in [`anti_genericity_appendix.md`](anti_genericity_appendix.md).

```text
Neo4j Schema for CTI: ATT&CK + CISA KEV + NVD

The schema has three source domains: threat behavior (ATT&CK), vulnerabilities (NVD, KEV, CWE), and your environment (organization, assets, controls). Two bridges connect them. The first runs from CVEs to the threat groups and software that exploit them. The second runs from CVEs to ATT&CK techniques, so mitigations can be traced back to vulnerability exposure.

Node labels and key properties

ATT&CK domain (ingested from the MITRE STIX 2.1 bundles)

Label    Key properties    Notes
:Tactic    attackId (TA0001), name, shortname (initial-access), stixId    
:Technique    attackId (T1190), name, description, platforms[], isSubtechnique, stixId, version, revoked, deprecated    Sub-techniques also get the label :SubTechnique
:Group    attackId (G0016), name, aliases[], description, stixId, revoked, deprecated    From STIX intrusion-set
:Software    attackId (S0154), name, type (malware/tool), aliases[], platforms[], stixId    Also labeled :Malware or :Tool
:Campaign    attackId (C0024), name, firstSeen, lastSeen, stixId    
:Mitigation    attackId (M1051), name, description, stixId    From STIX course-of-action

Vulnerability domain (from NVD CVE API 2.0, the KEV JSON feed, MITRE CWE/CAPEC, and FIRST EPSS)

Label    Key properties    Notes
:CVE    id (CVE-2023-4966), description, published, lastModified, vulnStatus, cvssVersion, cvssBaseScore, cvssSeverity, cvssVector, attackVector, epssScore, epssPercentile, inKEV (bool)    inKEV is copied from the KEV node for fast filtering
:KEVEntry    cveId, vendorProject, product, vulnerabilityName, dateAdded, dueDate, requiredAction, knownRansomwareCampaignUse, notes    A separate node keeps KEV provenance and history clean
:CWE    id (CWE-787), name, abstraction    
:CAPEC    id (CAPEC-66), name, likelihood, severity    Optional bridge from CWE to ATT&CK
:CPE    uri (cpe:2.3:a:citrix:netscaler_adc:13.1-49.13:...), part, vendor, product, version, update    One node per concrete product version
:Product    key (citrix:netscaler_adc), vendor, product, displayName    Version-independent product
:Vendor    name    

Environment domain (from your CMDB or asset scanner)

Label    Key properties
:Organization    id, name
:Asset    id, hostname, type, internetFacing (bool), criticality (1–5), environment (prod/dev)
:Sector (optional)    name, used for group-targeting enrichment from threat reports
Relationship types (with direction)

Inside ATT&CK

Pattern    Properties
(:Technique)-[:IN_TACTIC]->(:Tactic)    
(:SubTechnique)-[:SUBTECHNIQUE_OF]->(:Technique)    
(:Group)-[:USES]->(:Technique)    description, source, stixId
(:Group)-[:USES]->(:Software)    description, source
(:Software)-[:USES]->(:Technique)    description
(:Campaign)-[:ATTRIBUTED_TO]->(:Group)    
(:Campaign)-[:USES]->(:Technique) and (:Campaign)-[:USES]->(:Software)    
(:Mitigation)-[:MITIGATES]->(:Technique)    description

Threat to vulnerability (bridge 1)

Pattern    Properties
(:Group)-[:EXPLOITS]->(:CVE)    source (ATT&CK reference, vendor report URL), confidence (high/med/low), firstObserved
(:Software)-[:EXPLOITS]->(:CVE)    same
(:Campaign)-[:EXPLOITS]->(:CVE)    same
(:Group)-[:TARGETS]->(:Sector) (optional)    source

ATT&CK has no structured CVE field. CVE IDs appear only in free-text descriptions and external references, so populate EXPLOITS by extracting CVE IDs with a regex over those texts, plus any commercial or OSINT intel feeds you have. Record a source on every edge.

Vulnerability to technique (bridge 2)

Pattern    Properties
(:CVE)-[:ENABLES]->(:Technique)    mappingType (exploitation_technique / primary_impact / secondary_impact), source (CTID Mappings Explorer, analyst)
(:CVE)-[:HAS_WEAKNESS]->(:CWE)    source (nvd / cna)
(:CWE)-[:CHILD_OF]->(:CWE)    
(:CAPEC)-[:TARGETS_WEAKNESS]->(:CWE)    
(:CAPEC)-[:MAPS_TO]->(:Technique)    

Vulnerability to product

Pattern    Properties
(:CVE)-[:AFFECTS]->(:CPE)    vulnerable, matchCriteriaId, versionStartIncluding, versionEndExcluding (kept for audit)
(:CVE)-[:IN_KEV]->(:KEVEntry)    
(:KEVEntry)-[:REPORTS_PRODUCT]->(:Product)    Fallback when NVD has no CPE configuration yet
(:CPE)-[:VERSION_OF]->(:Product)    
(:Product)-[:MADE_BY]->(:Vendor)    

Environment

Pattern    Properties
(:Organization)-[:OWNS]->(:Asset)    
(:Organization)-[:IN_SECTOR]->(:Sector)    
(:Asset)-[:RUNS]->(:CPE)    discoveredAt, source (scanner name)
(:Organization)-[:IMPLEMENTS]->(:Mitigation)    status (implemented / partial / planned), coverage (0–1), lastAssessed
(:Asset)-[:EXPOSED_TO]->(:CVE) (derived)    riskScore, computedAt, patched (bool)
Constraints and indexes
cypher
CREATE CONSTRAINT cve_id     IF NOT EXISTS FOR (n:CVE)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT tech_id    IF NOT EXISTS FOR (n:Technique)  REQUIRE n.attackId IS UNIQUE;
CREATE CONSTRAINT group_id   IF NOT EXISTS FOR (n:Group)      REQUIRE n.attackId IS UNIQUE;
CREATE CONSTRAINT sw_id      IF NOT EXISTS FOR (n:Software)   REQUIRE n.attackId IS UNIQUE;
CREATE CONSTRAINT mit_id     IF NOT EXISTS FOR (n:Mitigation) REQUIRE n.attackId IS UNIQUE;
CREATE CONSTRAINT tactic_id  IF NOT EXISTS FOR (n:Tactic)     REQUIRE n.attackId IS UNIQUE;
CREATE CONSTRAINT cpe_uri    IF NOT EXISTS FOR (n:CPE)        REQUIRE n.uri IS UNIQUE;
CREATE CONSTRAINT prod_key   IF NOT EXISTS FOR (n:Product)    REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT cwe_id     IF NOT EXISTS FOR (n:CWE)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kev_cve    IF NOT EXISTS FOR (n:KEVEntry)   REQUIRE n.cveId IS UNIQUE;
CREATE CONSTRAINT asset_id   IF NOT EXISTS FOR (n:Asset)      REQUIRE n.id IS UNIQUE;
CREATE INDEX cve_kev   IF NOT EXISTS FOR (n:CVE) ON (n.inKEV);
CREATE INDEX stix_tech IF NOT EXISTS FOR (n:Technique) ON (n.stixId);
CREATE INDEX stix_grp  IF NOT EXISTS FOR (n:Group) ON (n.stixId);
CREATE FULLTEXT INDEX groupNames IF NOT EXISTS FOR (n:Group) ON EACH [n.name, n.aliases];
Query 1: Which threat groups could exploit my products?

This query returns evidence tiers so analysts can separate “has exploited this exact CVE” from “uses a technique this CVE enables.”

cypher
MATCH (o:Organization {id: $orgId})-[:OWNS]->(a:Asset)-[e:EXPOSED_TO]->(c:CVE)
WHERE NOT e.patched
CALL (c) {
  MATCH (g:Group)-[:EXPLOITS]->(c)
  RETURN g, 'direct' AS evidence, 3 AS weight
  UNION
  MATCH (g:Group)-[:USES]->(:Software)-[:EXPLOITS]->(c)
  RETURN g, 'via_software' AS evidence, 2 AS weight
  UNION
  MATCH (g:Group)<-[:ATTRIBUTED_TO]-(:Campaign)-[:EXPLOITS]->(c)
  RETURN g, 'via_campaign' AS evidence, 2 AS weight
  UNION
  MATCH (c)-[r:ENABLES {mappingType: 'exploitation_technique'}]->(t:Technique)<-[:USES]-(g:Group)
  RETURN g, 'technique_overlap' AS evidence, 1 AS weight
}
WITH g, a, c, evidence, weight
WHERE NOT coalesce(g.revoked, false) AND NOT coalesce(g.deprecated, false)
RETURN g.attackId AS group, g.name AS name,
       collect(DISTINCT evidence)          AS evidenceTypes,
       count(DISTINCT c)                   AS exploitableCVEs,
       count(DISTINCT a)                   AS assetsAtRisk,
       sum(weight * c.cvssBaseScore)       AS threatScore,
       collect(DISTINCT c.id)[..10]        AS sampleCVEs
ORDER BY threatScore DESC
LIMIT 25;

The CALL (c) { ... } syntax requires Neo4j 5.23 or later. On older versions, use CALL { WITH c ... } instead.

Query 2: Which mitigations reduce the most risk?

This query ranks ATT&CK mitigations you have not yet implemented by the total risk of the exposures they address.

cypher
MATCH (o:Organization {id: $orgId})-[:OWNS]->(a:Asset)-[e:EXPOSED_TO]->(c:CVE)
WHERE NOT e.patched
MATCH (c)-[:ENABLES]->(t:Technique)
OPTIONAL MATCH (t)-[:SUBTECHNIQUE_OF]->(parent:Technique)
WITH o, a, c, e, [x IN [t, parent] WHERE x IS NOT NULL] AS techs
UNWIND techs AS tech
MATCH (m:Mitigation)-[:MITIGATES]->(tech)
WHERE NOT EXISTS { (o)-[:IMPLEMENTS {status: 'implemented'}]->(m) }
// optional threat weighting: techniques used by groups that target you count more
OPTIONAL MATCH (tech)<-[:USES]-(g:Group)
WITH m, a, c, e.riskScore AS risk, count(DISTINCT g) AS groupsUsingTech
WITH DISTINCT m, a, c, risk * (1 + 0.05 * least(groupsUsingTech, 10)) AS weightedRisk
RETURN m.attackId AS mitigation, m.name AS name,
       count(*)          AS exposuresAddressed,
       count(DISTINCT c) AS cvesAddressed,
       round(sum(weightedRisk), 2) AS riskReduced
ORDER BY riskReduced DESC
LIMIT 15;

The DISTINCT on (m, a, c) stops one exposure from being counted several times when a mitigation covers several of its techniques.

Design notes

Do version matching at ingest, not in Cypher. NVD configurations express version ranges (versionStartIncluding, versionEndExcluding) over vendor-specific version strings. Comparing those in Cypher is slow and error-prone. Resolve them in your ETL with a proper version comparator, then write concrete (:CVE)-[:AFFECTS]->(:CPE) edges and the derived EXPOSED_TO edges.

Use a simple, explainable riskScore on EXPOSED_TO. A reasonable starting formula is cvssBaseScore/10 × likelihood × asset.criticality × exposureFactor. Set likelihood to 1.0 when the CVE is in KEV and to the EPSS score otherwise. Multiply by 1.25 when KEV reports ransomware use. Set exposureFactor to 1.5 for internet-facing assets with network attack vectors. Recompute nightly when KEV, EPSS, and NVD refresh.

Keep technique overlap as the weakest evidence. Techniques like T1190 (Exploit Public-Facing Application) are used by dozens of groups, so overlap alone would flag almost everyone. Restrict it to exploitation_technique mappings and weight it below direct evidence, as Query 1 does.

Rank patching ahead of ATT&CK mitigations. ATT&CK mitigations reduce the impact of techniques; they don’t remove the vulnerability. Your UI should surface the KEV requiredAction and dueDate for KEV-listed CVEs before compensating controls.

Rank mitigations as a portfolio, not one at a time. Mitigations overlap heavily (for example, M1051 Update Software and M1050 Exploit Protection cover similar exposures). To choose a set of mitigations, run Query 2 greedily: pick the top one, mark its exposures as covered, and re-rank. You can do this in application code or with a weighted set-cover heuristic.

Ingest ATT&CK versions with STIX IDs as keys. ATT&CK releases revoke, deprecate, and renumber objects. Keep stixId on every node and filter out revoked and deprecated objects in queries. If you load multiple domains (Enterprise, ICS, Mobile), add a domain property or a domain label.

Store provenance on bridge edges. Every inferred or extracted edge (EXPLOITS, ENABLES, MAPS_TO) should carry source and confidence. Analysts can then filter by trust level, and you can rebuild one source’s edges without touching the others.
```
