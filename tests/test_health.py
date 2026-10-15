"""Tests for the health endpoints."""
# pylint: disable=missing-function-docstring

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable

from app.database.connection import get_driver
from app.main import app
from tests.fakes import FakeDriver

client = TestClient(app)

COMPONENTS = [{"name": "Neo4j Kernel", "version": "5.26.0", "edition": "community"}]


@pytest.fixture(name="use_driver")
def fixture_use_driver():
    def install(driver):
        app.dependency_overrides[get_driver] = lambda: driver

    yield install
    app.dependency_overrides.clear()


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_version(use_driver):
    use_driver(FakeDriver(lambda query, parameters: COMPONENTS))
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "neo4j_version": "5.26.0", "neo4j_edition": "community"}


@pytest.mark.parametrize("error", [ServiceUnavailable("bolt://secret-host:7687 refused"), AuthError("bad password")])
def test_database_health_returns_503_without_leaking_details(use_driver, error):
    def responder(query, parameters):
        raise error

    use_driver(FakeDriver(responder))
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "Neo4j is unavailable"}


def test_lifespan_closes_driver(monkeypatch):
    closed = []
    monkeypatch.setattr("app.main.close_driver", lambda: closed.append(True))
    with TestClient(app):
        pass
    assert closed == [True]
