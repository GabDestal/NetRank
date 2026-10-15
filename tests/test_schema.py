"""Tests for app.database.schema."""
# pylint: disable=missing-function-docstring

import re

from app.database import schema
from tests.fakes import FakeDriver

# The constraints and indexes listed in docs/modeling_rationale.md, "Final schema".
EXPECTED = {
    ("constraint", label, prop)
    for label in ("Group", "Campaign", "Software", "Technique", "Tactic", "Mitigation")
    for prop in ("stix_id", "attack_id")
} | {
    ("constraint", "CVE", "cve_id"),
    ("constraint", "CWE", "cwe_id"),
    ("constraint", "Product", "product_key"),
    ("constraint", "Vendor", "vendor_key"),
    ("constraint", "ImportMeta", "source"),
    ("index", "CVE", "cvss_score"),
}

STATEMENT = re.compile(r"FOR \(n:(\w+)\) (?:REQUIRE |ON \()n\.(\w+)")


def test_schema_matches_the_documented_design():
    actual = set()
    for item in schema.SCHEMA:
        label, prop = STATEMENT.search(item.statement).groups()
        actual.add((item.kind, label, prop))
    assert actual == EXPECTED


def test_every_statement_is_idempotent_and_named_after_its_item():
    names = [item.name for item in schema.SCHEMA]
    assert len(names) == len(set(names))
    for item in schema.SCHEMA:
        assert "IF NOT EXISTS" in item.statement
        assert f" {item.name} IF NOT EXISTS" in item.statement
        assert ("IS UNIQUE" in item.statement) == (item.kind == "constraint")


def test_apply_schema_runs_each_statement_once_in_order():
    driver = FakeDriver()
    names = schema.apply_schema(driver)
    assert [q for q, _, _ in driver.queries] == [item.statement for item in schema.SCHEMA]
    assert names == [item.name for item in schema.SCHEMA]


def test_missing_schema_reports_absent_items():
    present = [{"name": item.name} for item in schema.SCHEMA[:-2]]

    def responder(query, _parameters):
        return present if query.startswith("SHOW CONSTRAINTS") else [{"name": "some_other_index"}]

    assert schema.missing_schema(FakeDriver(responder)) == [item.name for item in schema.SCHEMA[-2:]]


def test_missing_schema_is_empty_when_everything_exists():
    names = [{"name": item.name} for item in schema.SCHEMA]
    assert not schema.missing_schema(FakeDriver(lambda query, parameters: names))
