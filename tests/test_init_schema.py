"""Tests for scripts.init_schema."""
# pylint: disable=missing-function-docstring

from neo4j.exceptions import ServiceUnavailable

from app.database.schema import SCHEMA
from scripts import common, init_schema
from tests.fakes import FakeDriver


def install(monkeypatch, driver):
    closed = []
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: closed.append(True))
    return closed


def test_main_applies_and_verifies_schema(monkeypatch):
    names = [{"name": item.name} for item in SCHEMA]
    driver = FakeDriver(lambda query, parameters: names if query.startswith("SHOW") else [])
    closed = install(monkeypatch, driver)
    assert init_schema.main() == 0
    assert sum(q.startswith("CREATE") for q, _, _ in driver.queries) == len(SCHEMA)
    assert closed == [True]


def test_main_fails_when_items_are_missing(monkeypatch):
    install(monkeypatch, FakeDriver())
    assert init_schema.main() == 1


def test_main_fails_when_neo4j_is_down(monkeypatch):
    def responder(query, parameters):
        raise ServiceUnavailable("down")

    closed = install(monkeypatch, FakeDriver(responder))
    assert init_schema.main() == 1
    assert closed == [True]
