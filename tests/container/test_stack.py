"""End-to-end health of the compose stack: nginx -> api -> neo4j, and Docker's own healthchecks."""

import json
import shutil
import subprocess

import pytest

from tests.conftest import skip_or_fail

pytestmark = pytest.mark.container

SERVICES = {"neo4j", "api", "nginx"}


def test_nginx_answers_its_own_probe(http):
    """nginx serves its health location without hitting the API."""
    response = http.get("/nginx-health")
    assert response.status_code == 200


def test_api_ready_through_the_proxy(http):
    """The full chain works: nginx proxies to the API, which reaches Neo4j with GDS loaded."""
    response = http.get("/api/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_swagger_is_served_through_the_proxy(http):
    """Swagger UI and the OpenAPI document are reachable behind nginx."""
    assert http.get("/docs").status_code == 200
    assert http.get("/openapi.json").json()["info"]["title"] == "NetRank API"


@pytest.mark.usefixtures("http")
def test_docker_reports_every_service_healthy():
    """`docker compose ps` shows the three services running and healthy (skipped with the stack down)."""
    if shutil.which("docker") is None:
        skip_or_fail("docker CLI not available")
    output = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"], capture_output=True, text=True, check=True
    ).stdout
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    health = {row["Service"]: row.get("Health") for row in rows}
    assert SERVICES <= set(health), health
    assert all(health[name] == "healthy" for name in SERVICES), health
