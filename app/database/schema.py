"""Constraints and indexes of the ThreatGraph schema (docs/modeling_rationale.md, "Final schema").

Schema statements (DDL) cannot take labels or property names as query parameters, so each one
is written out in full here instead of being assembled from strings. Every statement uses
IF NOT EXISTS, which makes apply_schema safe to run any number of times.

Each uniqueness constraint also creates a range index on its property, so a lookup such as
MATCH (g:Group {attack_id: $id}) is an index seek, O(log n), instead of a label scan, O(n).
"""

from dataclasses import dataclass

from neo4j import Driver, RoutingControl


@dataclass(frozen=True)
class SchemaItem:
    """One named constraint or index and the statement that creates it."""

    name: str
    kind: str  # "constraint" or "index"
    statement: str


SCHEMA: tuple[SchemaItem, ...] = (
    # D1: STIX id is the import join key, ATT&CK id is the lookup key. Both unique per label.
    SchemaItem("group_stix_id", "constraint",
               "CREATE CONSTRAINT group_stix_id IF NOT EXISTS FOR (n:Group) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("group_attack_id", "constraint",
               "CREATE CONSTRAINT group_attack_id IF NOT EXISTS FOR (n:Group) REQUIRE n.attack_id IS UNIQUE"),
    SchemaItem("campaign_stix_id", "constraint",
               "CREATE CONSTRAINT campaign_stix_id IF NOT EXISTS FOR (n:Campaign) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("campaign_attack_id", "constraint",
               "CREATE CONSTRAINT campaign_attack_id IF NOT EXISTS FOR (n:Campaign) REQUIRE n.attack_id IS UNIQUE"),
    # D5: every :Malware and :Tool node also carries :Software, so these cover both.
    SchemaItem("software_stix_id", "constraint",
               "CREATE CONSTRAINT software_stix_id IF NOT EXISTS FOR (n:Software) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("software_attack_id", "constraint",
               "CREATE CONSTRAINT software_attack_id IF NOT EXISTS FOR (n:Software) REQUIRE n.attack_id IS UNIQUE"),
    # D3: sub-techniques are :Technique:SubTechnique, so these cover both.
    SchemaItem("technique_stix_id", "constraint",
               "CREATE CONSTRAINT technique_stix_id IF NOT EXISTS FOR (n:Technique) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("technique_attack_id", "constraint",
               "CREATE CONSTRAINT technique_attack_id IF NOT EXISTS FOR (n:Technique) REQUIRE n.attack_id IS UNIQUE"),
    SchemaItem("tactic_stix_id", "constraint",
               "CREATE CONSTRAINT tactic_stix_id IF NOT EXISTS FOR (n:Tactic) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("tactic_attack_id", "constraint",
               "CREATE CONSTRAINT tactic_attack_id IF NOT EXISTS FOR (n:Tactic) REQUIRE n.attack_id IS UNIQUE"),
    SchemaItem("mitigation_stix_id", "constraint",
               "CREATE CONSTRAINT mitigation_stix_id IF NOT EXISTS FOR (n:Mitigation) REQUIRE n.stix_id IS UNIQUE"),
    SchemaItem("mitigation_attack_id", "constraint",
               "CREATE CONSTRAINT mitigation_attack_id IF NOT EXISTS FOR (n:Mitigation) "
               "REQUIRE n.attack_id IS UNIQUE"),
    # KEV, NVD and CTID all join on the CVE id.
    SchemaItem("cve_cve_id", "constraint",
               "CREATE CONSTRAINT cve_cve_id IF NOT EXISTS FOR (n:CVE) REQUIRE n.cve_id IS UNIQUE"),
    # D9
    SchemaItem("cwe_cwe_id", "constraint",
               "CREATE CONSTRAINT cwe_cwe_id IF NOT EXISTS FOR (n:CWE) REQUIRE n.cwe_id IS UNIQUE"),
    # D10
    SchemaItem("product_product_key", "constraint",
               "CREATE CONSTRAINT product_product_key IF NOT EXISTS FOR (n:Product) REQUIRE n.product_key IS UNIQUE"),
    SchemaItem("vendor_vendor_key", "constraint",
               "CREATE CONSTRAINT vendor_vendor_key IF NOT EXISTS FOR (n:Vendor) REQUIRE n.vendor_key IS UNIQUE"),
    # D2: one metadata node per source.
    SchemaItem("importmeta_source", "constraint",
               "CREATE CONSTRAINT importmeta_source IF NOT EXISTS FOR (n:ImportMeta) REQUIRE n.source IS UNIQUE"),
    # D8: range index for filtering and sorting by severity (WHERE c.cvss_score >= 9, ORDER BY c.cvss_score).
    SchemaItem("cve_cvss_score", "index",
               "CREATE RANGE INDEX cve_cvss_score IF NOT EXISTS FOR (n:CVE) ON (n.cvss_score)"),
)


def apply_schema(driver: Driver) -> list[str]:
    """Create every constraint and index that does not exist yet. Returns the names handled."""
    for item in SCHEMA:
        driver.execute_query(item.statement)
    return [item.name for item in SCHEMA]


def existing_schema(driver: Driver) -> set[str]:
    """Return the names of the constraints and indexes currently in the database."""
    constraints, _, _ = driver.execute_query("SHOW CONSTRAINTS YIELD name RETURN name",
                                             routing_=RoutingControl.READ)
    indexes, _, _ = driver.execute_query("SHOW INDEXES YIELD name RETURN name", routing_=RoutingControl.READ)
    return {record["name"] for record in constraints} | {record["name"] for record in indexes}


def missing_schema(driver: Driver) -> list[str]:
    """Return the names of schema items that are expected but absent from the database."""
    present = existing_schema(driver)
    return [item.name for item in SCHEMA if item.name not in present]
