"""API tests for the liveness and readiness endpoints, with Neo4j faked."""

from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable

SERVER = [{"version": "5.26.32", "edition": "community"}]


def test_liveness_does_not_touch_the_database(api_client, fake_db_factory):
    """GET /api/health answers 200 without issuing any query."""
    fake = fake_db_factory({})
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not fake.calls


def test_readiness_ok_when_gds_is_loaded(api_client, fake_db_factory):
    """Neo4j up and GDS present gives 200 with both versions."""
    fake_db_factory({"dbms.components": SERVER, "gds.version": [{"version": "2.13.4"}]})
    response = api_client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "neo4j_version": "5.26.32",
        "neo4j_edition": "community",
        "gds_version": "2.13.4",
    }


def test_readiness_degraded_when_gds_is_missing(api_client, fake_db_factory):
    """An unknown gds.version() function gives 503 with status 'degraded'."""
    fake_db_factory({"dbms.components": SERVER, "gds.version": ClientError("Unknown function 'gds.version'")})
    response = api_client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["gds_version"] is None


def test_readiness_503_when_neo4j_is_down(api_client, fake_db_factory):
    """An unreachable server gives 503 with a message naming the failure, not a 500."""
    fake_db_factory({"dbms.components": ServiceUnavailable("connection refused")})
    response = api_client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Neo4j unavailable (ServiceUnavailable)"}


def test_readiness_503_on_bad_credentials(api_client, fake_db_factory):
    """Rejected credentials give 503 and do not leak the server's message."""
    fake_db_factory({"dbms.components": AuthError("The client is unauthorized")})
    response = api_client.get("/api/health/ready")
    assert response.status_code == 503
    assert "unauthorized" not in response.text


def test_openapi_lists_the_health_routes(api_client):
    """Swagger is generated and documents both probes."""
    paths = api_client.get("/openapi.json").json()["paths"]
    assert {"/api/health", "/api/health/ready"} <= set(paths)
