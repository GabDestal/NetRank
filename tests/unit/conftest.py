"""Fixtures for unit tests that must not open a real Neo4j connection."""

from unittest.mock import MagicMock

import pytest

from app.database import client as client_module


@pytest.fixture
def driver(monkeypatch):
    """Replace GraphDatabase.driver with a MagicMock and return the mock driver.

    The factory itself is exposed as `driver.factory` to assert on constructor arguments.
    """
    mock_driver = MagicMock()
    factory = MagicMock(return_value=mock_driver)
    monkeypatch.setattr(client_module.GraphDatabase, "driver", factory)
    mock_driver.factory = factory
    return mock_driver
