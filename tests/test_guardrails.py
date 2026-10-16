"""Tests for the Cypher guardrails (D19): static checks, LIMIT enforcement, EXPLAIN and guarded execution."""
# pylint: disable=missing-function-docstring

import pytest
from neo4j import READ_ACCESS
from neo4j.exceptions import ClientError, CypherSyntaxError, Neo4jError

from app.agent import guardrails
from app.agent.guardrails import MAX_ROWS, GuardrailError, check_cypher, explain, run_guarded
from tests.fakes import FakeSessionDriver


def rule_of(query):
    with pytest.raises(GuardrailError) as caught:
        check_cypher(query)
    return caught.value.rule


@pytest.mark.parametrize("query", [
    "MATCH (n) DETACH DELETE n",
    "MATCH (c:CVE) SET c.cvss_score = 0 RETURN c",
    "MATCH (c:CVE) REMOVE c.name RETURN c",
    "MATCH (a:Group) MERGE (a)-[:USES]->(:Technique {attack_id: 'T9999'}) RETURN a",
    "MATCH (n) CALL dbms.killQueries(['x']) RETURN n",
    "MATCH (n) CALL { CREATE (:X) } RETURN n",
    "WITH 1 AS x CALL apoc.cypher.runWrite('CREATE (:X)', {}) YIELD value RETURN value",
    "MATCH (n) FOREACH (x IN [1] | CREATE (:X)) RETURN n",
    "MATCH (n:CVE) RETURN n.cve_id UNION MATCH (g:Group) RETURN g.attack_id",
    "match (n) detach delete n return 1",
])
def test_writes_procedures_and_unions_are_rejected(query):
    assert rule_of(query) == "forbidden_keyword"


@pytest.mark.parametrize("query, rule", [
    ("", "empty"),
    ("   ;  ", "empty"),
    ("CREATE (n:X) RETURN n", "not_a_read_clause"),
    ("SHOW USERS", "not_a_read_clause"),
    ("DROP CONSTRAINT cve_id", "not_a_read_clause"),
    ("LOAD CSV FROM 'file:///x' AS row RETURN row", "not_a_read_clause"),
    ("EXPLAIN MATCH (n) RETURN n", "not_a_read_clause"),
    ("MATCH (n) RETURN n; MATCH (m) DETACH DELETE m", "multiple_statements"),
    ("MATCH (n:CVE) WHERE n.cvss_score > 9", "no_return"),
    ("MATCH (n) RETURN n LIMIT $n", "limit_not_literal"),
    ("MATCH (n) RETURN n " + "x" * 2000, "too_long"),
])
def test_other_rejections_name_their_rule(query, rule):
    assert rule_of(query) == rule


def test_keywords_inside_strings_comments_and_property_names_are_not_rejected():
    query = ("MATCH (c:CVE) // delete nothing\n"
             "WHERE c.name CONTAINS 'Remote Code Execution; DROP TABLE' AND c.set IS NULL AND $delete IS NULL "
             "/* CREATE */ RETURN c.cve_id AS `create` LIMIT 5")
    assert check_cypher(query) == query


def test_limit_is_added_when_missing_and_lowered_when_too_high():
    assert check_cypher("MATCH (n:CVE) RETURN n.cve_id;") == f"MATCH (n:CVE) RETURN n.cve_id\nLIMIT {MAX_ROWS}"
    assert check_cypher("MATCH (n:CVE) RETURN n.cve_id LIMIT 10000").endswith(f"LIMIT {MAX_ROWS}")
    assert check_cypher("MATCH (n:CVE) RETURN n.cve_id limit 5") == "MATCH (n:CVE) RETURN n.cve_id limit 5"


def test_limit_inside_a_subquery_still_gets_a_final_limit():
    query = "MATCH (g:Group) WITH g LIMIT 5 RETURN g.name"
    assert check_cypher(query).endswith(f"LIMIT {MAX_ROWS}")


def test_string_literals_are_extracted():
    assert guardrails.string_literals("MATCH (w:CWE {cwe_id: 'CWE-79'}) WHERE x = \"T1190\" RETURN 1") == \
        ["CWE-79", "T1190"]


def explaining(answer):
    return FakeSessionDriver(session_responder=lambda query, parameters: answer)


def test_explain_accepts_a_read_only_plan_in_a_read_session():
    driver = explaining({"query_type": "r"})
    explain(driver, "MATCH (n) RETURN n LIMIT 1")
    text, _, config, _ = driver.session_queries[0]
    assert text == "EXPLAIN MATCH (n) RETURN n LIMIT 1"
    assert config["default_access_mode"] == READ_ACCESS and config["notifications_disabled_categories"] == []


@pytest.mark.parametrize("query_type", ["rw", "w", "s"])
def test_explain_rejects_plans_that_are_not_read_only(query_type):
    with pytest.raises(GuardrailError) as caught:
        explain(explaining({"query_type": query_type}), "MATCH (n) RETURN n")
    assert caught.value.rule == "explain_not_read_only"


def test_explain_reports_unknown_labels_briefly():
    notification = {"code": "Neo.ClientNotification.Statement.UnknownLabelWarning",
                    "description": "One of the labels ... (the missing label name is: Vulnerability)"}
    with pytest.raises(GuardrailError) as caught:
        explain(explaining({"notifications": [notification, {"code": "Other", "description": "ignored"}]}),
                "MATCH (v:Vulnerability) RETURN v")
    assert caught.value.rule == "explain_unknown_schema"
    assert caught.value.reason.startswith("unknown label: Vulnerability")


@pytest.mark.parametrize("error, rule", [
    (CypherSyntaxError("Invalid input 'RETRUN'"), "explain_syntax"),
    (ClientError("Variable `x` not defined"), "explain_failed"),
])
def test_explain_turns_server_errors_into_rejections(error, rule):
    def responder(query, parameters):
        raise error

    with pytest.raises(GuardrailError) as caught:
        explain(FakeSessionDriver(session_responder=responder), "MATCH (n) RETURN x")
    assert caught.value.rule == rule


def test_run_guarded_checks_explains_then_runs_with_timeout_and_row_cap():
    rows = [{"id": i} for i in range(MAX_ROWS + 10)]
    driver = FakeSessionDriver(session_responder=lambda query, parameters: {"rows": rows})
    result = run_guarded(driver, "MATCH (n:CVE) RETURN n.cve_id AS id")
    assert len(result.rows) == MAX_ROWS and result.query.endswith(f"LIMIT {MAX_ROWS}")
    explained, executed = driver.session_queries[0], driver.session_queries[1]
    assert explained[0].startswith("EXPLAIN ") and executed[0] == result.query
    assert executed[2]["default_access_mode"] == READ_ACCESS and executed[3] == guardrails.TIMEOUT_SECONDS


def test_run_guarded_never_reaches_the_database_for_a_write():
    driver = FakeSessionDriver()
    with pytest.raises(GuardrailError):
        run_guarded(driver, "MATCH (n) DETACH DELETE n")
    assert not driver.session_queries


@pytest.mark.parametrize("code, rule", [
    ("Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration", "timeout"),
    ("Neo.ClientError.Statement.ArithmeticError", "runtime_error"),
])
def test_run_guarded_reports_timeouts_and_runtime_errors(code, rule):
    def responder(query, _parameters):
        if query.startswith("EXPLAIN"):
            return {"query_type": "r"}
        raise Neo4jError._hydrate_neo4j(code=code, message="failed")  # pylint: disable=protected-access

    with pytest.raises(GuardrailError) as caught:
        run_guarded(FakeSessionDriver(session_responder=responder), "MATCH (n) RETURN 1/0")
    assert caught.value.rule == rule
