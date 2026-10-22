"""Admin API-key checks on POST /api/admin/gds/refresh (refresh itself is stubbed)."""

import pytest

from app import security
from app.config import Settings
from app.services import gds

URL = "/api/admin/gds/refresh"
REPORT = {"prestige": {}, "styles": {}, "concurrency": 1, "minMatches": 50, "seconds": 0.1}


@pytest.fixture(name="admin_settings")
def fixture_admin_settings(monkeypatch, fake_db_factory):
    """Server key 'right-key'; refresh stubbed so no database is needed."""
    fake_db_factory({})
    calls = []
    monkeypatch.setattr(security, "get_settings", lambda: Settings(admin_api_key="right-key"))
    monkeypatch.setattr(gds, "refresh", lambda db: calls.append(db) or REPORT)
    return calls


def test_missing_key_is_401(api_client, admin_settings):
    """No X-API-Key header: 401 with a WWW-Authenticate hint; refresh not called."""
    response = api_client.post(URL)
    assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "ApiKey"
    assert not admin_settings


def test_wrong_key_is_403(api_client, admin_settings):
    """A key that does not match: 403; refresh not called."""
    assert api_client.post(URL, headers={"X-API-Key": "wrong-key"}).status_code == 403
    assert not admin_settings


def test_right_key_runs_refresh(api_client, admin_settings):
    """The configured key: 200 and the refresh report."""
    response = api_client.post(URL, headers={"X-API-Key": "right-key"})
    assert response.status_code == 200 and response.json()["minMatches"] == 50
    assert len(admin_settings) == 1


def test_unconfigured_server_disables_admin(api_client, fake_db_factory, monkeypatch):
    """Without ADMIN_API_KEY on the server every call is 503, whatever key is sent."""
    fake_db_factory({})
    monkeypatch.setattr(security, "get_settings", lambda: Settings(admin_api_key=None))
    assert api_client.post(URL, headers={"X-API-Key": "anything"}).status_code == 503


def test_comparison_is_constant_time(monkeypatch):
    """The key check goes through secrets.compare_digest."""
    seen = []
    monkeypatch.setattr(security, "get_settings", lambda: Settings(admin_api_key="right-key"))
    monkeypatch.setattr(security.secrets, "compare_digest", lambda a, b: seen.append((a, b)) or True)
    security.require_admin_key("guess")
    assert seen == [(b"guess", b"right-key")]
