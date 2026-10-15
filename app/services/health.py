"""Database health checks."""

from neo4j import Driver, RoutingControl

# dbms.components() is a read-only system procedure that reports the server name, version and
# edition. It touches no graph data, so its cost does not grow with the graph.
COMPONENTS_QUERY = (
    "CALL dbms.components() YIELD name, versions, edition "
    "RETURN name, versions[0] AS version, edition"
)


def neo4j_components(driver: Driver) -> dict[str, str]:
    """Return the Neo4j server's version and edition. Raises the driver's error if unreachable."""
    records, _, _ = driver.execute_query(COMPONENTS_QUERY, routing_=RoutingControl.READ)
    kernel = next((r for r in records if r["name"] == "Neo4j Kernel"), records[0])
    return {"version": kernel["version"], "edition": kernel["edition"]}
