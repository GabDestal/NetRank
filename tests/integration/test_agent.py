"""Guardrail layers against the real server, and a scripted agent run on synthetic data (no Groq)."""

from datetime import date

import pytest
from neo4j.exceptions import ClientError

from app.agent import graph, guardrails
from app.agent.replay import ReplayLLM
from scripts import demo_guardrail, ingest

pytestmark = pytest.mark.integration

A, B = -41, -42
CLEANUP = """
MATCH (n)
WHERE (n:Player AND n.id IN [-41, -42]) OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TESTAG-')
   OR n:GuardProbe
DETACH DELETE n
"""


@pytest.fixture(name="agent_graph")
def fixture_agent_graph(neo4j_client):
    """Two synthetic players with a 2-1 head-to-head."""
    db = neo4j_client
    db.write(CLEANUP)
    ingest.ensure_schema(db)
    players = [{"id": A, "name": "Agenttest Alpha"}, {"id": B, "name": "Agenttest Bravo"}]
    ingest.load(db, ingest.MERGE_PLAYERS, players, "p")
    ingest.load(db, ingest.MERGE_TOURNAMENTS, [{"id": "TESTAG-T", "name": "Agent Open", "year": 1905}], "t")
    rows = [
        {
            "id": f"TESTAG-T-{n}",
            "tournamentId": "TESTAG-T",
            "date": date(1905, 1, n),
            "round": "R32",
            "bestOf": 3,
            "score": "6-3 6-4",
            "minutes": 70,
            "surface": "Clay",
            "walkover": False,
            "retired": False,
            "winnerId": w,
            "loserId": l,
            "winner": {},
            "loser": {},
        }
        for n, (w, l) in enumerate([(A, B), (A, B), (B, A)], start=1)
    ]
    ingest.load(db, ingest.MERGE_MATCHES, rows, "m")
    db.write("CALL db.awaitIndexes(60)")
    yield db
    db.write(CLEANUP)


def test_read_mode_transaction_rejects_writes_on_its_own(agent_graph):
    """Layer 5 alone: even a write that skipped every check is refused by the server."""
    with pytest.raises(ClientError, match="read access mode"):
        agent_graph.read_only("CREATE (:GuardProbe) RETURN 1 AS one", {}, timeout=5.0, max_rows=1)
    assert not agent_graph.read("MATCH (g:GuardProbe) RETURN g")


def test_explain_layer_on_the_server(agent_graph):
    """The real planner exposes write operators, syntax errors and unknown property keys."""
    for query, reason in [
        ("MATCH (p:Player) SET p.flag = true RETURN count(p)", "write operators"),
        ("MATCH (p:Player RETURN p", "syntax error"),
        ("MATCH (p:Player) RETURN p.nmae LIMIT 1", "property key does not exist"),
    ]:
        with pytest.raises(guardrails.GuardrailError, match=reason):
            guardrails.explain_check(agent_graph, query)


def test_guarded_cypher_runs_reads_with_limit(agent_graph):
    """A legitimate fallback query runs with the LIMIT added."""
    result = guardrails.run_readonly(
        agent_graph, "MATCH (p:Player)-[:WON]->(m:Match) WHERE p.id = -41 RETURN m.id AS id ORDER BY id"
    )
    assert [row["id"] for row in result["rows"]] == ["TESTAG-T-1", "TESTAG-T-2"]
    assert result["cypher"].endswith("LIMIT 50")


def test_scripted_agent_end_to_end(agent_graph):
    """Resolve both names, read the head-to-head, answer; a wrong number is downgraded by the verifier."""
    turns = [
        {
            "content": "",
            "tool_calls": [
                {"name": "search_player", "args": {"name": "Agenttest Alpha"}, "id": "a"},
                {"name": "search_player", "args": {"name": "Agenttest Bravo"}, "id": "b"},
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {"name": "head_to_head", "args": {"player1_id": A, "player2_id": B}, "id": "c"},
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {
                    "name": "submit_answer",
                    "id": "d",
                    "args": {
                        "kind": "answer",
                        "summary": "Alpha leads Bravo 2-1.",
                        "claims": [
                            {"text": "Alpha leads the head-to-head 2-1.", "type": "verified", "sources": ["t3"]},
                            {"text": "Alpha won 5 matches against Bravo.", "type": "verified", "sources": ["t3"]},
                        ],
                    },
                }
            ],
        },
    ]
    question = "What is Agenttest Alpha's record against Agenttest Bravo?"
    response = graph.ask(agent_graph, ReplayLLM(turns), question, 8, "scripted")
    assert [record.tool for record in response.trace] == ["search_player", "search_player", "head_to_head"]
    assert response.trace[2].result["player1Wins"] == 2
    assert [c.tag for c in response.answer.claims] == ["verified", "interpreted"]
    assert response.downgradedClaims == 1


def test_demo_replays_the_write_through_every_layer(agent_graph):
    """make demo-guardrail: static, EXPLAIN and the READ transaction each stop the write on their own."""
    write = "MATCH (p:Player) SET p.name = 'hacked' RETURN count(p)"
    verdicts = dict(demo_guardrail.layer_by_layer(agent_graph, write))
    assert verdicts["1 static"].startswith("REJECTS") and verdicts["3 explain"].startswith("REJECTS")
    assert "AccessMode" in verdicts["5 READ transaction"]
    source, turns = demo_guardrail.load(demo_guardrail.DEFAULT)
    assert "Scripted" in source and turns[0]["tool_calls"][0]["name"] == "run_readonly_cypher"


def test_unknown_property_rejection_names_the_real_keys(agent_graph):
    """The EXPLAIN rejection of a wrong property guess tells the model which keys exist."""
    with pytest.raises(guardrails.GuardrailError, match="Match: id, date, round.*minutes"):
        guardrails.explain_check(agent_graph, "MATCH (m:Match) RETURN max(m.duration)")
