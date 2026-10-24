"""Unit tests for the Cypher and scope guardrails (EXPLAIN layer with a fake client)."""

import pytest
from neo4j.exceptions import CypherSyntaxError

from app.agent import guardrails as g


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("MATCH (n) DETACH DELETE n", "DETACH"),
        ("MATCH (p:Player) SET p.name = 'x'", "SET"),
        ("CREATE (:Player {id: 1})", "CREATE"),
        ("MERGE (p:Player {id: 1}) RETURN p", "MERGE"),
        ("MATCH (p:Player) REMOVE p.name", "REMOVE"),
        ("LOAD CSV FROM 'file:///etc/passwd' AS line RETURN line", "LOAD CSV"),
        ("MATCH (n) CALL (n) { DELETE n } IN TRANSACTIONS", "DELETE"),
        ("DROP INDEX player_name", "DROP"),
        ("RETURN 1; MATCH (n) RETURN n", "one statement"),
        ("CALL dbms.listConfig() YIELD name RETURN name", "dbms.listConfig"),
        ("CALL gds.pageRank.stream('g') YIELD nodeId RETURN nodeId", "gds.pageRank.stream"),
        ("call apoc.periodic.iterate('a', 'b', {})", "apoc.periodic.iterate"),
        ("   ", "empty"),
    ],
)
def test_static_layer_rejects_writes_and_unknown_procedures(query, reason):
    """Write clauses, LOAD CSV, several statements and non-allow-listed procedures never reach the server."""
    with pytest.raises(g.GuardrailError, match=reason) as error:
        g.static_check(query)
    assert error.value.layer == "static"


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (p:Player {name: 'Set Point; DELETE everything'}) RETURN p.id",  # keywords inside a string
        "MATCH (p:Player) // DELETE in a comment\nRETURN p.name",
        "CALL () { MATCH (m:Match) RETURN count(m) AS c } RETURN c",  # subquery, not a procedure
        "CALL db.index.fulltext.queryNodes('player_name_ft', 'nadal*') YIELD node RETURN node.name",
        "MATCH (p:Player) RETURN p.name;",  # one trailing semicolon is fine
    ],
)
def test_static_layer_accepts_reads(query):
    """Reads pass, including write words inside strings or comments and allow-listed procedures."""
    assert g.static_check(query)


def test_schema_layer():
    """Only NetRank labels and relationship types; multi-type patterns are split."""
    g.schema_check("MATCH (p:Player)-[:WON|LOST]->(m:Match)-[:PART_OF]->(t:Tournament) RETURN t")
    with pytest.raises(g.GuardrailError, match="Playr"):
        g.schema_check("MATCH (p:Playr) RETURN p")
    with pytest.raises(g.GuardrailError, match="BEATS"):
        g.schema_check("MATCH (a:Player)-[r:BEATS*1..2]->(b) RETURN b")


@pytest.mark.parametrize(
    ("query", "text", "limit"),
    [
        ("MATCH (p:Player) RETURN p.name", "MATCH (p:Player) RETURN p.name\nLIMIT 50", 50),
        ("MATCH (p:Player) RETURN p.name LIMIT 5", "MATCH (p:Player) RETURN p.name LIMIT 5", 5),
        ("MATCH (p:Player) RETURN p.name LIMIT 5000", "MATCH (p:Player) RETURN p.name LIMIT 50", 50),
    ],
)
def test_limit_layer(query, text, limit):
    """LIMIT appended when missing and lowered when above the cap."""
    checked = g.enforce_limit(query)
    assert (checked.text, checked.limit) == (text, limit)


class FakeExplainDb:
    """Returns a fixed plan and notifications, or raises, for EXPLAIN."""

    def __init__(self, plan=None, notifications=(), error=None, rows=()):
        """Configure the EXPLAIN outcome and the rows read_only returns."""
        self.plan = plan or {"operatorType": "ProduceResults@neo4j", "children": []}
        self.notifications = list(notifications)
        self.error = error
        self.rows = list(rows)
        self.executed = []

    def explain(self, _query, _params):
        """Fake EXPLAIN."""
        if self.error:
            raise self.error
        return self.plan, self.notifications

    def read_only(self, query, params, timeout, max_rows):
        """Fake guarded execution: records the call."""
        self.executed.append((query, params, timeout, max_rows))
        return self.rows[:max_rows]


def test_explain_layer_rejects_syntax_errors_writes_and_unknown_schema():
    """Syntax errors, write operators in the plan and server schema warnings are rejected."""
    syntax = CypherSyntaxError("Invalid input 'RETURN'")
    with pytest.raises(g.GuardrailError, match="syntax error") as error:
        g.explain_check(FakeExplainDb(error=syntax), "MATCH (p RETURN p")
    assert error.value.layer == "explain"
    plan = {"operatorType": "ProduceResults@neo4j", "children": [{"operatorType": "SetProperty@neo4j"}]}
    with pytest.raises(g.GuardrailError, match="SetProperty"):
        g.explain_check(FakeExplainDb(plan=plan), "MATCH (p:Player) RETURN p")
    codes = [("01N52", "warn: property key does not exist. The property `nmae` does not exist")]
    with pytest.raises(g.GuardrailError, match="property key does not exist"):
        g.explain_check(FakeExplainDb(notifications=codes), "MATCH (p:Player) RETURN p.nmae")


def test_run_readonly_executes_checked_query_with_caps():
    """A valid query runs once, with the LIMIT applied, the timeout and the row cap."""
    db = FakeExplainDb(rows=[{"n": i} for i in range(100)])
    result = g.run_readonly(db, "MATCH (p:Player) RETURN p.name AS n")
    assert result["rowCount"] == 50 and result["cypher"].endswith("LIMIT 50")
    assert db.executed[0][2:] == (g.TIMEOUT_SECONDS, 50)


@pytest.mark.parametrize(
    ("question", "betting"),
    [
        ("Should I bet on Sinner?", True),
        ("How much should I stake on the final?", True),
        ("Give me a tip for tomorrow", True),
        ("Who is the better player on clay?", False),
        ("What probability does the model give Sinner?", False),
        ("What are Pinnacle's odds for the 2019 final?", False),
        ("What did Pinnacle give Federer in the 2019 Wimbledon semi?", False),
        ("How does the model compare with the bookmakers?", False),
        ("Which bookmaker had the lowest margin in 2015?", False),
    ],
)
def test_betting_scope(question, betting):
    """Betting and staking requests are detected; probability questions are not."""
    assert g.asks_for_betting_advice(question) is betting


def test_betting_advice_in_output():
    """Generated recommendations are detected."""
    assert g.contains_betting_advice("You should bet on Sinner at 1.80.")
    assert not g.contains_betting_advice("Pinnacle gave Sinner 0.55 without margin.")


def test_property_hint_lists_keys_of_the_labels_in_the_query():
    """After an unknown-property rejection the model sees the real keys of the labels it used."""
    hint = g.property_hint("MATCH (p:Player)-[:WON]->(m:Match) RETURN m.duration")
    assert "Match: id, date, round" in hint and "minutes" in hint and "WON:" in hint
    assert "Bookmaker" not in hint and "PRICED" not in hint
    assert "Bookmaker" in g.property_hint("MATCH (n) RETURN n.x")  # no label: everything


def test_explain_feedback_names_the_neo4j_5_syntax():
    """exists(x.prop) and size((pattern)) were removed in Neo4j 5: the rejection says what to write (D78)."""
    syntax = CypherSyntaxError("The property existence syntax `... exists(variable.property)` is no longer supported")
    with pytest.raises(g.GuardrailError, match="IS NOT NULL") as error:
        g.explain_check(FakeExplainDb(error=syntax), "MATCH (m:Match) WHERE exists(m.minutes) RETURN m")
    assert "COUNT {" not in str(error.value)
    assert "COUNT {" in g.syntax_hint("MATCH (p:Player) RETURN size((p)-[:WON]->())")
    assert g.syntax_hint("MATCH (m:Match) WHERE m.minutes IS NOT NULL RETURN m") == ""
    assert g.syntax_hint("MATCH (p:Player {name: 'exists(x.y)'}) RETURN p") == ""


def test_syntax_hints_come_from_a_fixed_list_and_never_echo_graph_data():
    """Review of #38: hints are constant strings; names, ids and property names in the query never appear in them."""
    fixed = [hint for _, hint in g.SYNTAX_HINTS]
    assert all(isinstance(hint, str) for hint in fixed)
    query = (
        "MATCH (p:Player {name: 'Roger Federer'}) WHERE exists(p.secretProp) AND p.id = 103819 "
        + "RETURN size((p)-[:WON]->(:Match {score: '7-6(7) 1-6 7-6(4)'})) AS wins"
    )
    hint = g.syntax_hint(query)
    assert hint.startswith(". Hint: ")
    assert set(hint.removeprefix(". Hint: ").split("; ")) <= set(fixed)
    for value in ("Federer", "103819", "secretProp", "7-6", "wins"):
        assert value not in hint
