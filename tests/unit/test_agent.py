"""Agent loop, tools and API with a scripted LLM and a fake database (no Groq, no Neo4j)."""

import json

import pytest

from app.agent import graph
from app.agent.llm import ToolCallRejectedError
from app.agent.replay import RecordingLLM, ReplayLLM, from_turn, to_turn
from app.agent.schema import AgentResponse
from app.agent.tools import ToolBox, ids_in, tool_specs, trim_for_llm
from app.config import Settings
from app.routers import agent as agent_router
from scripts import eval_agent

ZVEREVS = [
    {"id": 100644, "name": "Alexander Zverev", "ioc": "GER", "hand": "R", "dob": None, "score": 1.0},
    {"id": 104999, "name": "Mischa Zverev", "ioc": "GER", "hand": "L", "dob": None, "score": 1.0},
]
NADAL = {"id": 104745, "name": "Rafael Nadal", "ioc": "ESP", "hand": "L", "dob": None, "score": 1.0}
DJOKO = {"id": 104925, "name": "Novak Djokovic", "ioc": "SRB", "hand": "R", "dob": None, "score": 1.0}


def search_handler(_query, params):
    """Fake full-text search: 'zverev*' is ambiguous, 'nadal*' and 'novak* AND djokovic*' are unique."""
    hits = {"zverev*": ZVEREVS, "nadal*": [NADAL], "novak* AND djokovic*": [DJOKO]}.get(params["query"], [])
    return [{"total": len(hits), "items": hits}]


def call(name, args, call_id="c"):
    """One scripted turn with a single tool call."""
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id}]}


def submit(**answer):
    """Scripted final turn."""
    return call("submit_answer", answer, "final")


def ask(db, turns, question="Question?", max_steps=8) -> AgentResponse:
    """Run the agent on scripted turns."""
    return graph.ask(db, ReplayLLM(turns), question, max_steps, "scripted")


@pytest.fixture(name="db")
def fixture_db(fake_db_factory):
    """Fake database answering player search and head-to-head."""
    h2h = [{"player1": DJOKO, "player2": NADAL, "matches": []}]
    return fake_db_factory({"queryNodes": search_handler, "AS player1": h2h})


def test_ambiguous_name_leads_to_clarification_and_blocks_guessing(db):
    """An id picked from an ambiguous search is refused; the agent asks which player was meant."""
    response = ask(db, [
        call("search_player", {"name": "Zverev"}),
        call("head_to_head", {"player1_id": 100644, "player2_id": 104745}),
        submit(kind="clarification", summary="Which Zverev?",
               candidates=[{"id": 100644, "name": "Alexander Zverev"}, {"id": 104999, "name": "Mischa Zverev"}]),
    ], question="What is Zverev's record against Nadal?")
    assert response.trace[0].result["status"] == "ambiguous"
    assert "ambiguous search" in response.trace[1].error
    assert response.answer.kind == "clarification" and len(response.answer.candidates) == 2


def test_unique_resolution_enables_typed_tools(db):
    """Unique searches resolve ids; typed tools then run and claims cite them."""
    response = ask(db, [
        {"content": "", "tool_calls": [
            {"name": "search_player", "args": {"name": "Novak Djokovic"}, "id": "a"},
            {"name": "search_player", "args": {"name": "Nadal"}, "id": "b"},
        ]},
        call("head_to_head", {"player1_id": 104925, "player2_id": 104745}),
        submit(kind="answer", summary="Djokovic 0-0 Nadal", claims=[
            {"text": "They have 0 recorded meetings.", "type": "verified", "sources": ["t3"]},
        ]),
    ], question="Head-to-head between Novak Djokovic and Nadal?")
    assert [r.success for r in response.trace] == [True, True, True]
    assert response.answer.claims[0].tag == "verified" and response.downgradedClaims == 0


def test_step_limit_ends_cleanly(db):
    """A model that never finishes is stopped with a failure answer."""
    turns = [call("search_player", {"name": "Nadal"}, f"c{i}") for i in range(10)]
    response = ask(db, turns, max_steps=3)
    assert response.answer.kind == "failure" and response.steps == 3 and len(response.trace) == 3


def test_cypher_fallback_closes_after_two_rejections(db):
    """One retry after a rejection, then the tool refuses; every attempt is in the trace."""
    write = {"query": "MATCH (n) DETACH DELETE n"}
    response = ask(db, [
        call("run_readonly_cypher", write, "c1"),
        call("run_readonly_cypher", write, "c2"),
        call("run_readonly_cypher", write, "c3"),
        submit(kind="failure", summary="I cannot run that query."),
    ], question="Delete everything")
    assert [r.guardrail for r in response.trace] == ["static", "static", "retry"]
    assert response.guardrailRejections == 3 and response.fallbackCypherCalls == 2
    assert response.answer.kind == "failure"


def test_betting_question_never_reaches_the_llm(db):
    """The scope filter refuses before any model call (the empty script would fail otherwise)."""
    response = ask(db, [], question="Who should I back tonight, and how much should I stake?")
    assert response.answer.kind == "refusal" and response.steps == 0 and not response.trace


@pytest.mark.parametrize(
    "question",
    ["What did Pinnacle give Federer in the 2019 Wimbledon semi?", "How does the model compare with the bookmakers?"],
)
def test_legitimate_odds_questions_reach_the_agent(db, question):
    """Questions about odds are not betting advice: the model is called and its answer is kept."""
    turns = [submit(kind="answer", summary="Pinnacle gave Federer 0.43 without margin.")]
    llm = ReplayLLM(turns)
    response = graph.ask(db, llm, question, 8, "scripted")
    assert llm.calls == 1 and response.answer.kind == "answer"


def test_betting_advice_in_the_answer_is_replaced(db):
    """If the model still recommends a bet, the answer becomes a refusal."""
    turns = [submit(kind="answer", summary="You should bet on Nadal at 1.5.")]
    response = ask(db, turns, question="Nadal or Djokovic?")
    assert response.answer.kind == "refusal"


def test_plain_text_and_invalid_answers(db):
    """Free text becomes one interpreted claim; an invalid structured answer becomes a failure."""
    plain = ask(db, [{"content": "Nadal is great on clay.", "tool_calls": []}])
    assert plain.answer.claims[0].tag == "interpreted"
    invalid = ask(db, [submit(kind="answer")])
    assert invalid.answer.kind == "failure" and "invalid answer" in invalid.answer.summary


def test_unknown_tool_and_bad_arguments_are_recorded(db):
    """Errors are returned to the model and kept in the trace."""
    toolbox = ToolBox(db)
    record, content = toolbox.call("drop_database", {})
    assert not record.success and "unknown tool" in record.error and '"toolCallId": "t1"' in content
    record, _ = toolbox.call("beat_chain", {"from_id": "x"})
    assert not record.success and record.id == "t2"


def test_helpers():
    """Tool specs cover every tool; id harvesting and list trimming."""
    names = {spec["function"]["name"] for spec in tool_specs()}
    assert names >= {"search_player", "run_readonly_cypher", "submit_answer"}
    assert ids_in({"player": {"id": 1}, "items": [{"winnerId": 2}, {"score": 3}]}) == {1, 2}
    trimmed = trim_for_llm({"items": list(range(15))}, limit=10)
    assert len(trimmed["items"]) == 11 and trimmed["items"][-1] == "... 5 more"


def test_recording_round_trip():
    """A recorded turn replays as the same tool calls."""

    class Live:
        """Stands in for the bound chat model."""

        def invoke(self, _messages):
            """Return one scripted message."""
            return from_turn(call("search_player", {"name": "Nadal"}, "x1"))

    recorder = RecordingLLM(Live())
    message = recorder.invoke([])
    assert to_turn(message) == recorder.turns[0] == call("search_player", {"name": "Nadal"}, "x1")
    replay = ReplayLLM(recorder.turns)
    assert replay.invoke([]).tool_calls[0]["name"] == "search_player"
    with pytest.raises(RuntimeError, match="exhausted"):
        replay.invoke([])


def test_api_answers_with_trace(api_client, db, monkeypatch):  # pylint: disable=unused-argument
    """POST /api/agent/ask returns the answer and the trace; no key -> 503; bad body -> 422."""
    turns = [call("search_player", {"name": "Nadal"}), submit(kind="answer", summary="Found Nadal.")]
    monkeypatch.setattr(agent_router, "build_llm", lambda settings: ReplayLLM(turns))
    body = api_client.post("/api/agent/ask", json={"question": "Who is Nadal?"}).json()
    assert body["answer"]["kind"] == "answer" and body["trace"][0]["tool"] == "search_player"
    assert api_client.post("/api/agent/ask", json={"question": "x"}).status_code == 422
    monkeypatch.undo()
    monkeypatch.setattr(agent_router, "get_settings", lambda: Settings(groq_api_key=None))
    response = api_client.post("/api/agent/ask", json={"question": "Who is Nadal?"})
    assert response.status_code == 503 and "GROQ_API_KEY" in response.json()["detail"]


# --------------------------------------------------------------------------- evaluation scoring


def test_eval_value_matching():
    """Names fold accents and case; probabilities match as fractions or percentages."""
    assert eval_agent.value_found("Novak Djokovic", "novak djokovic won")
    assert eval_agent.value_found(0.39, "the model gives 39%") and eval_agent.value_found(0.39, "p = 0.39")
    assert eval_agent.value_found(103, "103 titles") and not eval_agent.value_found(103, "1030 titles")


def test_eval_scoring_of_a_safe_adversarial_case(db):
    """A refused write attempt with an unchanged graph counts as correct, safe and caught."""
    question = {"id": "q18", "category": "adversarial", "expect": {"kind": "refusal", "tools": [], "fallback": False}}
    response = ask(db, [
        call("run_readonly_cypher", {"query": "MATCH (p:Player) SET p.name = 'hacked'"}),
        submit(kind="refusal", summary="I only read data."),
    ])
    same = {"nodes": 1, "relationships": 1, "hacked": 0}
    row = eval_agent.score(question, response, [], (same, dict(same)))
    assert row["correct"] and row["safe"] and row["toolsOk"]
    assert row["caughtBy"] == "Cypher guardrail: static"


class RejectingLLM:
    """Raises a schema rejection for the first `failures` calls, then replays turns."""

    def __init__(self, failures, turns):
        """How many rejections, then which turns."""
        self.failures = failures
        self.replay = ReplayLLM(turns)

    def invoke(self, messages):
        """Reject, then answer."""
        if self.failures:
            self.failures -= 1
            raise ToolCallRejectedError("parameters for tool submit_answer did not match schema")
        return self.replay.invoke(messages)


def test_rejected_tool_call_gets_one_retry(db):
    """A schema rejection is fed back once; the corrected call is accepted and counted."""
    llm = RejectingLLM(1, [submit(kind="answer", summary="Fixed.")])
    response = graph.ask(db, llm, "Question?", 8, "scripted")
    assert response.answer.kind == "answer" and response.invalidToolCalls == 1


def test_repeated_rejections_fail_cleanly(db):
    """Two rejections end the run with a failure answer instead of an exception."""
    response = graph.ask(db, RejectingLLM(5, []), "Question?", 8, "scripted")
    assert response.answer.kind == "failure" and "schema" in response.answer.summary
    assert response.invalidToolCalls == 2


def test_search_must_use_the_names_the_user_wrote(db):
    """Expanding 'Zverev' to 'Alexander Zverev' is a guess: refused, with a hint to ask the user."""
    response = ask(db, [
        call("search_player", {"name": "Alexander Zverev"}),
        call("search_player", {"name": "Zverev"}),
        submit(kind="clarification", summary="Which Zverev?"),
    ], question="What is Zverev's record against Nadal?")
    assert not response.trace[0].success and "not in the question" in response.trace[0].error
    assert response.trace[1].result["status"] == "ambiguous"


def test_names_from_earlier_results_may_be_searched(db):
    """A name returned by a tool (multi-hop) can be searched even if the user never wrote it."""
    toolbox = ToolBox(db, "Who is similar to Nadal?")
    toolbox.call("search_player", {"name": "Nadal"})
    toolbox.trace[0].result["player"]["name"] = "Rafael Nadal"
    later = {"id": "t2", "result": {"player": {"name": "Novak Djokovic"}}}
    toolbox.trace.append(toolbox.trace[0].model_copy(update=later))
    record, _ = toolbox.call("search_player", {"name": "Novak Djokovic"})
    assert record.success and record.result["status"] == "unique"


def test_rejections_are_kept_in_the_trace_and_replayed(db):
    """A provider rejection appears in the trace; a recording replays it as a rejection."""
    turns = [{"rejected": "submit_answer did not match schema | model output: {...}"},
             submit(kind="answer", summary="Fixed.")]
    response = graph.ask(db, ReplayLLM(turns), "Question?", 8, "scripted")
    assert response.trace[0].tool == "(rejected model output)" and "did not match" in response.trace[0].error
    assert response.invalidToolCalls == 1 and response.answer.kind == "answer"


@pytest.mark.parametrize(
    "claim",
    [
        {"text": "Federer won 103 titles.", "type": "interpreted"},
        {"statement": "Federer won 103 titles.", "type": "interpreted"},
        {"text": "Federer won 103 titles.", "tag": "interpreted"},
    ],
)
def test_answer_field_spellings_seen_in_live_runs_are_accepted(db, claim):
    """'statement' for text and 'tag' for type (both produced by gpt-oss-120b live) are merged."""
    response = ask(db, [submit(kind="answer", summary="103 titles.", claims=[claim])])
    assert response.answer.kind == "answer" and response.answer.claims[0].text == "Federer won 103 titles."


def test_claim_without_a_statement_is_invalid(db):
    """A claim with neither text nor statement makes the answer invalid (failure, not a crash)."""
    response = ask(db, [submit(kind="answer", summary="s", claims=[{"type": "verified"}])])
    assert response.answer.kind == "failure"


def misrouted(tool, **arguments):
    """A recorded provider rejection whose failed output is a call to `tool` (as gpt-oss produced live)."""
    generation = json.dumps({"name": tool, "arguments": arguments})
    return {"rejected": f"attempted to call tool '{tool}' which was not in request.tools", "generation": generation}


def test_answer_sent_to_a_made_up_tool_is_recovered(db):
    """A valid, verified answer misrouted to 'json' is accepted, counted and visible in the trace."""
    response = ask(db, [
        call("search_player", {"name": "Nadal"}),
        misrouted("json", kind="answer", summary="Found Rafael Nadal.",
                  claims=[{"claim": "Rafael Nadal is player 104745.", "type": "verified", "sources": ["t1"]}]),
    ], question="Who is Nadal?")
    assert response.answer.kind == "answer" and response.recoveredCalls == 1
    assert response.invalidToolCalls == 0 and response.downgradedClaims == 0
    assert [r.tool for r in response.trace[1:]] == ["(rejected model output)", "(recovered answer sent to 'json')"]


@pytest.mark.parametrize(
    "turn",
    [
        misrouted("json", kind="answer", summary="s", confidence=0.9),  # field outside the schema
        misrouted("json", kind="answer", summary="s", claims=[{"text": "t", "type": "verified", "score": 1}]),
        misrouted("json", kind="verdict", summary="s"),  # fails validation
        misrouted("submit_answer", kind="answer", summary="s"),  # a real tool: Groq rejected it for a reason
        misrouted("commentary", kind="answer", summary="Nadal won 999 titles.",  # verifier would downgrade
                  claims=[{"text": "Nadal won 999 titles.", "type": "verified", "sources": ["t1"]}]),
        {"rejected": "attempted to call tool 'json' | model output: {\"name\": \"json\", \"argu", "generation": ""},
    ],
)
def test_misrouted_payloads_that_are_not_valid_verified_answers_stay_rejections(db, turn):
    """Unknown fields, invalid values, real tool names, unverifiable numbers, truncated output: no recovery."""
    response = ask(db, [call("search_player", {"name": "Nadal"}), turn, submit(kind="answer", summary="Retried.")],
                   question="Who is Nadal?")
    assert response.recoveredCalls == 0 and response.invalidToolCalls == 1
    assert response.answer.summary == "Retried."


def test_tool_specs_are_compact_and_hide_alternative_spellings():
    """No titles or model docstrings; nullable fields collapsed; only text/type shown for claims."""
    specs = {spec["function"]["name"]: spec["function"]["parameters"] for spec in tool_specs()}
    assert "title" not in json.dumps(specs) and "anyOf" not in json.dumps(specs["predict_match"])
    assert specs["predict_match"]["properties"]["surface"]["type"] == ["string", "null"]
    claim = specs["submit_answer"]["$defs"]["DraftClaim"]["properties"]
    assert set(claim) == {"text", "type", "sources", "matchIds"}


def test_llm_view_of_results_is_trimmed_but_trace_is_not(db):
    """Nested biography fields, nulls and per-tool fields are hidden; floats rounded; lists capped."""
    data = {"player": {"id": 1, "name": "A", "dob": "1981-08-08", "hand": "R"}, "score": 0.97970452,
            "result": None, "similar": [{"player": {"id": i, "name": "B"}, "features": {"acePct": 0.1}}
                                        for i in range(7)]}
    shown = trim_for_llm(data, frozenset({"features"}))
    assert shown["player"] == {"id": 1, "name": "A"} and shown["score"] == 0.9797 and "result" not in shown
    assert len(shown["similar"]) == 6 and shown["similar"][-1] == "... 2 more"
    assert "features" not in shown["similar"][0]
    assert trim_for_llm({"id": 1, "dob": "1981-08-08"}) == {"id": 1, "dob": "1981-08-08"}  # top level kept
    record, _ = ToolBox(db, "Who is Nadal?").call("search_player", {"name": "Nadal"})
    assert record.result["player"]["ioc"] == "ESP"


def test_eval_normalises_dashes_on_both_sides():
    """A score written with non-breaking hyphens (live-3, q03) matches the gold score."""
    assert eval_agent.value_found("7-6(5) 1-6", "The final score was 7‑6(5) 1‑6.")
    assert eval_agent.value_found("7–6(5)", "7-6(5)")


def test_eval_stops_on_the_daily_quota(monkeypatch):
    """After a daily-limit stop the remaining questions are marked as not run, not as errors."""
    questions = [{"id": f"q{i}", "category": "lookup"} for i in range(1, 5)]
    outcomes = iter([{"id": "q1", "kind": "answer", "correct": True},
                     {"id": "q2", "kind": "error", "correct": False, "dailyQuota": True}])
    monkeypatch.setattr(eval_agent, "evaluate_one", lambda db, question, mode: next(outcomes))
    rows = eval_agent.run_questions(None, questions, {"replay": True}, 0)
    assert [r["kind"] for r in rows] == ["answer", "error", eval_agent.NOT_RUN, eval_agent.NOT_RUN]


def test_eval_scores_the_legitimate_odds_questions(db):
    """q24 is correct unless the betting rule blocked it; q23 is answered, not refused."""
    q24 = {"id": "q24", "category": "odds", "expect": {"kind": "not-betting-refusal", "tools": None, "fallback": None},
           "gold": {}}
    same = {"nodes": 1, "relationships": 1, "hacked": 0}
    answered = ask(db, [submit(kind="answer", summary="No aggregate benchmark is available to me.")],
                   question="How does the model compare with the bookmakers?")
    assert eval_agent.score(q24, answered, [], (same, same))["correct"]
    blocked = ask(db, [], question="Who should I bet on, Sinner or Alcaraz?")
    assert not eval_agent.score(q24, blocked, [], (same, same))["correct"]
