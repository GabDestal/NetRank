"""Question 1: which techniques a group uses, under which tactics, and which mitigations cover them."""

from neo4j import Driver, RoutingControl

from app.models.groups import GroupTechniquesResponse

# Finds the group by index seek on attack_id, O(log n), then walks its USES relationships to
# techniques, O(d) for a group using d techniques, and for each technique its tactics and
# mitigations, O(d x (tactics + mitigations per technique)). Cost depends on the group's degree,
# not on the size of the graph. Returns no row if the group does not exist.
GROUP_TECHNIQUES_QUERY = """
MATCH (g:Group {attack_id: $group_id})
RETURN g {.attack_id, .name, .aliases} AS group,
       COLLECT {
         MATCH (g)-[u:USES]->(t:Technique)
         RETURN t {.attack_id, .name, .is_subtechnique,
                   procedure: u.description, references: u.references,
                   tactics: COLLECT { MATCH (t)-[:IN_TACTIC]->(ta:Tactic) RETURN ta.name ORDER BY ta.order },
                   mitigations: COLLECT { MATCH (m:Mitigation)-[:MITIGATES]->(t)
                                          RETURN m {.attack_id, .name} ORDER BY m.attack_id }}
         ORDER BY t.attack_id
       } AS techniques
"""


def group_techniques(driver: Driver, group_id: str) -> GroupTechniquesResponse | None:
    """Return the group's techniques with tactics and mitigations, or None if there is no such group."""
    records, _, _ = driver.execute_query(GROUP_TECHNIQUES_QUERY, {"group_id": group_id},
                                         routing_=RoutingControl.READ)
    if not records:
        return None
    record = records[0]
    return GroupTechniquesResponse(group=record["group"], technique_count=len(record["techniques"]),
                                   techniques=record["techniques"])
