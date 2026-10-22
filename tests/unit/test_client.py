"""Unit tests for Neo4jClient with the driver replaced by a stub."""

from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from neo4j import NotificationMinimumSeverity, RoutingControl
from neo4j.time import Date

from app.config import Settings
from app.database.client import Neo4jClient, to_native
from app.main import app


def make_record(data):
    """A stand-in for neo4j.Record exposing only .data()."""
    record = MagicMock()
    record.data.return_value = data
    return record


def test_from_settings_passes_uri_and_secret(driver):
    """Settings are unwrapped into driver arguments, including the SecretStr password."""
    settings = Settings(neo4j_uri="bolt://db:7687", neo4j_user="u", neo4j_password="pw123456", neo4j_database="x")
    Neo4jClient.from_settings(settings)
    driver.factory.assert_called_once_with(
        "bolt://db:7687", auth=("u", "pw123456"), notifications_min_severity=NotificationMinimumSeverity.WARNING
    )


def test_read_routes_to_reader_and_returns_dicts(driver):
    """read() passes parameters separately and routes to a reader."""
    driver.execute_query.return_value = ([make_record({"n": 1})], None, None)
    rows = Neo4jClient("bolt://db", ("u", "p"), "neo4j").read("RETURN $n AS n", {"n": 1})
    assert rows == [{"n": 1}]
    driver.execute_query.assert_called_once_with(
        "RETURN $n AS n", {"n": 1}, database_="neo4j", routing_=RoutingControl.READ
    )


def test_write_routes_to_writer(driver):
    """write() routes to the writer and defaults params to an empty dict."""
    driver.execute_query.return_value = ([], None, None)
    Neo4jClient("bolt://db", ("u", "p"), "neo4j").write("CREATE ()")
    assert driver.execute_query.call_args.kwargs["routing_"] == RoutingControl.WRITE
    assert driver.execute_query.call_args.args[1] == {}


def test_profile_prefixes_query_and_returns_plan(driver):
    """profile() runs PROFILE on a reader and returns rows plus the plan tree."""
    summary = MagicMock(profile={"operatorType": "ProduceResults"})
    driver.execute_query.return_value = ([make_record({"n": 1})], summary, None)
    rows, plan = Neo4jClient("bolt://db", ("u", "p"), "neo4j").profile("RETURN 1 AS n")
    assert rows == [{"n": 1}] and plan == {"operatorType": "ProduceResults"}
    assert driver.execute_query.call_args.args[0] == "PROFILE RETURN 1 AS n"


def test_to_native_converts_nested_neo4j_temporals():
    """neo4j.time values inside dicts and lists become datetime.date."""
    value = {"d": Date(2019, 7, 14), "items": [{"d": Date(2000, 1, 3)}], "n": 3}
    assert to_native(value) == {"d": date(2019, 7, 14), "items": [{"d": date(2000, 1, 3)}], "n": 3}


def test_verify_and_close_delegate_to_driver(driver):
    """verify() and close() call the driver."""
    client = Neo4jClient("bolt://db", ("u", "p"), "neo4j")
    client.verify()
    client.close()
    driver.verify_connectivity.assert_called_once()
    driver.close.assert_called_once()


def test_lifespan_opens_and_closes_the_client(driver):
    """Starting the app creates the client on app.state; stopping it closes the driver."""
    with TestClient(app):
        assert isinstance(app.state.db, Neo4jClient)
    driver.close.assert_called_once()


def test_settings_hide_the_password():
    """The password never appears in the settings repr (e.g. in logs)."""
    settings = Settings(neo4j_password="supersecret1")
    assert "supersecret1" not in repr(settings)
