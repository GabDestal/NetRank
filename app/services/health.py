"""Readiness check: is Neo4j reachable, and is the GDS plugin loaded?"""

from neo4j.exceptions import ClientError

from app.database.client import Neo4jClient
from app.models.health import ReadinessResponse

SERVER_INFO = """
CALL dbms.components() YIELD name, versions, edition
WHERE name = 'Neo4j Kernel'
RETURN versions[0] AS version, edition
"""

GDS_VERSION = "RETURN gds.version() AS version"


def check_database(db: Neo4jClient) -> ReadinessResponse:
    """Query the server version, then the GDS version.

    Connection and authentication errors propagate to the caller. A missing GDS plugin is
    reported as a 'degraded' status rather than an error, since Neo4j itself is up.
    """
    server = db.read(SERVER_INFO)[0]
    try:
        gds_version = db.read(GDS_VERSION)[0]["version"]
    except ClientError:
        gds_version = None
    return ReadinessResponse(
        status="ok" if gds_version else "degraded",
        neo4j_version=server["version"],
        neo4j_edition=server["edition"],
        gds_version=gds_version,
    )
