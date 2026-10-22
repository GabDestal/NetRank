"""Shared fixtures: a fake Neo4j client for unit tests, a real one for integration tests."""

import os
from collections.abc import Callable, Iterator
from typing import Any

# Reproducible KNN/Louvain/FastRP: one GDS thread in every test run (set before settings are read).
os.environ.setdefault("GDS_CONCURRENCY", "1")

# pylint: disable=wrong-import-position
import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable

from app.config import get_settings
from app.database.client import Neo4jClient, get_db
from app.main import app

Handler = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


def skip_or_fail(reason: str) -> None:
    """Skip a test whose service is down, or fail it when NETRANK_REQUIRE_SERVICES=1 (set in CI)."""
    if os.environ.get("NETRANK_REQUIRE_SERVICES") == "1":
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


class FakeNeo4jClient:
    """Stands in for Neo4jClient. Each query is answered by the first handler whose key it contains."""

    def __init__(self, handlers: dict[str, Handler | list[dict[str, Any]] | Exception]) -> None:
        """Map a query substring to a result list, an exception to raise, or a callable."""
        self.handlers = handlers
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Record the call and return (or raise) the configured answer."""
        params = params or {}
        self.calls.append((query, params))
        for key, answer in self.handlers.items():
            if key in query:
                if isinstance(answer, Exception):
                    raise answer
                return answer(query, params) if callable(answer) else answer
        raise AssertionError(f"Unexpected query: {query}")

    write = read


@pytest.fixture
def fake_db_factory() -> Iterator[Callable[[dict], FakeNeo4jClient]]:
    """Install a FakeNeo4jClient as the get_db dependency; removed after the test."""

    def install(handlers: dict) -> FakeNeo4jClient:
        fake = FakeNeo4jClient(handlers)
        app.dependency_overrides[get_db] = lambda: fake
        return fake

    yield install
    app.dependency_overrides.clear()


@pytest.fixture
def api_client() -> TestClient:
    """HTTP client on the app without running the lifespan (no real driver is created)."""
    return TestClient(app)


@pytest.fixture(scope="session")
def neo4j_client() -> Iterator[Neo4jClient]:
    """A real client from the environment; skips the test when Neo4j is not reachable."""
    client = Neo4jClient.from_settings(get_settings())
    try:
        client.verify()
    except (ServiceUnavailable, AuthError, ValueError) as exc:
        client.close()
        skip_or_fail(f"Neo4j not reachable: {type(exc).__name__}")
    yield client
    client.close()
