"""Tests for app.database.connection."""
# pylint: disable=missing-function-docstring

import pytest

from app.database import connection
from tests.fakes import FakeDriver


@pytest.fixture(name="created")
def fixture_created(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://db.test:7687")
    monkeypatch.setenv("NEO4J_USER", "reader")
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    calls = []

    def fake_driver(uri, auth):
        driver = FakeDriver()
        calls.append((uri, auth, driver))
        return driver

    monkeypatch.setattr(connection.GraphDatabase, "driver", fake_driver)
    connection.close_driver()
    yield calls
    connection.close_driver()


def test_get_driver_uses_settings_and_is_shared(created):
    first = connection.get_driver()
    assert connection.get_driver() is first
    assert [(uri, auth) for uri, auth, _ in created] == [("bolt://db.test:7687", ("reader", "pw"))]


def test_close_driver_closes_and_allows_a_new_one(created):
    first = connection.get_driver()
    connection.close_driver()
    assert created[0][2].closed
    assert connection.get_driver() is not first
    assert len(created) == 2


def test_close_driver_without_driver_does_nothing(created):
    connection.close_driver()
    assert not created
