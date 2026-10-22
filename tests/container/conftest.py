"""Fixtures for the container tests: an HTTP client on the nginx entry point."""

import os

import httpx
import pytest

from tests.conftest import skip_or_fail

BASE_URL = os.environ.get("NETRANK_BASE_URL", f"http://localhost:{os.environ.get('NGINX_PORT', '8080')}")


@pytest.fixture(scope="session")
def http():
    """HTTP client on nginx; skips every container test when the stack is not up."""
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        try:
            client.get("/nginx-health")
        except httpx.TransportError:
            skip_or_fail(f"Compose stack not reachable at {BASE_URL}")
        yield client
