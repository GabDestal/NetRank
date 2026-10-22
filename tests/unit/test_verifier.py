"""Unit tests for the claim verifier."""

from app.agent.schema import AgentAnswer, Claim, ToolCallRecord
from app.agent.verifier import numbers_in_text, unsupported_numbers, verify

H2H = {
    "player1Wins": 30,
    "player2Wins": 28,
    "matches": [
        {"matchId": "2013-520-224", "date": "2013-05-31", "score": "6-4 3-6 6-2 6-7(3) 9-7"},
        {"matchId": "2019-540-225", "date": "2019-07-12", "score": "7-6(3) 1-6 6-3 6-4"},
    ],
}
TRACE = [
    ToolCallRecord(id="t1", tool="head_to_head", arguments={}, success=True, result=H2H),
    ToolCallRecord(id="t2", tool="predict_match", arguments={}, success=True, result={"p1WinProbability": 0.4289}),
    ToolCallRecord(id="t3", tool="run_readonly_cypher", arguments={}, success=True,
                   result={"cypher": "MATCH (m:Match) RETURN count(m) AS n\nLIMIT 50", "rows": [{"n": 102417}]}),
    ToolCallRecord(id="t4", tool="get_player", arguments={}, success=False, error="not found"),
]


def run(*claims: Claim):
    """Verify an answer made of the given claims."""
    return verify(AgentAnswer(kind="answer", summary="s", claims=list(claims)), TRACE)


def test_supported_numbers_stay_verified():
    """Numbers present as numeric fields, dates/scores/ids as whole strings, and years of cited dates."""
    answer, downgraded = run(
        Claim(text="Djokovic leads 30-28.", tag="verified", sources=["t1"]),
        Claim(text="They met on 2013-05-31: 6-4 3-6 6-2 6-7(3) 9-7.", tag="verified", sources=["t1"]),
        Claim(text="Their 2019 match was 2019-540-225.", tag="verified", sources=["t1"], matchIds=["2019-540-225"]),
        Claim(text="There are 102,417 matches.", tag="verified", sources=["t3"]),
    )
    assert downgraded == 0 and all(c.tag == "verified" for c in answer.claims)
    assert answer.claims[2].matchIds == ["2019-540-225"]
    assert answer.claims[3].cypher.startswith("MATCH (m:Match)")


def test_unsupported_numbers_are_downgraded():
    """A wrong count, a year no cited date has, or a number from an uncited call is downgraded."""
    answer, downgraded = run(
        Claim(text="Djokovic won 31 of their matches.", tag="verified", sources=["t1"]),
        Claim(text="They also met in 2021.", tag="verified", sources=["t1"]),
        Claim(text="Djokovic leads 30-28.", tag="verified", sources=["t2"]),
    )
    assert downgraded == 3 and all(c.tag == "interpreted" for c in answer.claims)
    assert answer.claims[0].downgradedFrom == "verified" and "31" in answer.claims[0].downgradeReason


def test_sources_must_exist_and_succeed():
    """No source, an unknown id, or a failed call cannot verify anything."""
    answer, downgraded = run(
        Claim(text="Federer won 103 titles.", tag="verified"),
        Claim(text="Federer won 103 titles.", tag="verified", sources=["t9"]),
        Claim(text="Federer won 103 titles.", tag="verified", sources=["t4"]),
    )
    assert downgraded == 3
    assert {c.downgradeReason for c in answer.claims} == {"no successful tool call cited"}


def test_predicted_claims_need_the_model():
    """Predicted claims citing predict_match stay; others are downgraded; percentages match fractions."""
    answer, downgraded = run(
        Claim(text="The model gives Federer 43%.", tag="predicted", sources=["t2"]),
        Claim(text="The model gives Federer 0.43.", tag="predicted", sources=["t1"]),
        Claim(text="Federer is the sentimental favourite.", tag="interpreted"),
    )
    assert downgraded == 1 and [c.tag for c in answer.claims] == ["predicted", "interpreted", "interpreted"]


def test_unknown_match_ids_are_dropped():
    """Match ids that appear in no cited result are removed from the claim."""
    answer, _ = run(Claim(text="See the final.", tag="verified", sources=["t1"], matchIds=["2019-540-225", "1999-1-1"]))
    assert answer.claims[0].matchIds == ["2019-540-225"]


def test_number_parsing():
    """Thousands separators, decimals and percentages."""
    assert numbers_in_text("1,211 wins, 0.43 and 43%") == [(1211.0, 0, False), (0.43, 2, False), (43.0, 0, True)]
    assert not unsupported_numbers("leads 30-28", [H2H])
