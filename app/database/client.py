"""Thin wrapper around the Neo4j Python driver.

The API owns one driver (one connection pool) for its whole lifetime. Every query goes through
`read`/`write` with parameters, never through string formatting.
"""

from typing import Any

from fastapi import Request
from neo4j import Driver, GraphDatabase, RoutingControl

from app.config import Settings


class Neo4jClient:
    """Owns a Neo4j driver and runs parameterised queries against one database."""

    def __init__(self, uri: str, auth: tuple[str, str], database: str) -> None:
        """Create the driver. No connection is opened until the first query."""
        self._driver: Driver = GraphDatabase.driver(uri, auth=auth)
        self._database = database

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jClient":
        """Build a client from the application settings."""
        auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
        return cls(settings.neo4j_uri, auth, settings.neo4j_database)

    def read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run a read query (routed to a reader) and return each record as a dict."""
        return self._run(query, params, RoutingControl.READ)

    def write(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run a write query (routed to the writer) and return each record as a dict."""
        return self._run(query, params, RoutingControl.WRITE)

    def verify(self) -> None:
        """Raise if the server is unreachable or the credentials are rejected."""
        self._driver.verify_connectivity()

    def close(self) -> None:
        """Close the driver and its connection pool."""
        self._driver.close()

    def _run(self, query: str, params: dict[str, Any] | None, routing: RoutingControl) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(
            query, params or {}, database_=self._database, routing_=routing
        )
        return [record.data() for record in records]


def get_db(request: Request) -> Neo4jClient:
    """FastAPI dependency: the client created at startup (overridden in tests)."""
    return request.app.state.db
