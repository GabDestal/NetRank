"""Connectivity and GDS checks against a real Neo4j instance."""

import pytest

from app.services.health import check_database

pytestmark = pytest.mark.integration


def test_parameterised_round_trip(neo4j_client):
    """A parameterised query reaches the server and comes back intact."""
    assert neo4j_client.read("RETURN $value AS value", {"value": 42}) == [{"value": 42}]


def test_server_is_neo4j_5(neo4j_client):
    """The project targets Neo4j 5.x."""
    assert check_database(neo4j_client).neo4j_version.startswith("5.")


def test_gds_plugin_is_loaded(neo4j_client):
    """The GDS plugin is installed, so readiness reports 'ok'."""
    result = check_database(neo4j_client)
    assert result.gds_version is not None
    assert result.status == "ok"
