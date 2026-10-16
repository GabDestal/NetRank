"""Tests for scripts.evaluate_agent and scripts.guardrail_demo."""
# pylint: disable=missing-function-docstring

import json

from app.agent.scripted import ScriptedChatModel, tool_call
from app.config import Settings
from app.models.agent import AgentResponse
from scripts import common, evaluate_agent, guardrail_demo
from tests.fakes import FakeSessionDriver


def response(answer, tools=(), citations=()):
    return AgentResponse(question="q", answer=answer, facts=[], citations=list(citations), stopped="answered",
                         provider="p", model="m", guardrail_events=[],
                         tool_calls=[{"step": 1, "tool": t, "arguments": {}, "status": "ok"} for t in tools])


def test_checks_cover_tools_citations_mentions_refusal_and_writes():
    spec = {"tools_any": ["mitigation_plan"], "cites_any": ["M1026"], "mentions_any": ["Privileged"]}
    good = response("Start with Privileged Account Management.", ["mitigation_plan"], ["m1026"])
    assert all(evaluate_agent.check(spec, good, unchanged=True).values())
    assert evaluate_agent.check(spec, response("No idea."), unchanged=False) == \
        {"graph_unchanged": False, "tools": False, "citations": False, "mentions": False}
    assert evaluate_agent.check({"refuses": True}, response("I cannot delete data: the graph is read-only."),
                                unchanged=True)["refuses"]


class FakeAgent:
    """Answers every question the same way."""

    def ask(self, question, **_model):
        return response(f"I cannot do that: {question}", ["run_cypher"])


def counting_driver():
    return FakeSessionDriver(lambda query, parameters: [{"nodes": 10, "relationships": 20}])


def test_evaluate_waits_between_questions_and_summarizes():
    questions = [{"id": "a", "kind": "core", "question": "q1", "tools_any": ["run_cypher"]},
                 {"id": "b", "kind": "adversarial", "question": "q2", "refuses": True},
                 {"id": "c", "kind": "core", "question": "q3", "mentions_any": ["absent"]}]
    waits = []
    report = evaluate_agent.evaluate(counting_driver(), FakeAgent(), questions, ("groq", "m"), delay=5,
                                     sleep=waits.append)
    assert waits == [5, 5]
    assert report["passed"] == 2 and report["total"] == 3 and report["pass_rate"] == 0.667
    assert report["by_kind"] == {"core": "1/2", "adversarial": "1/1"}


def test_question_file_is_well_formed():
    questions = json.loads(evaluate_agent.QUESTIONS_FILE.read_text(encoding="utf-8"))
    assert len(questions) >= 15 and len({q["id"] for q in questions}) == len(questions)
    assert sum(q["kind"] == "core" for q in questions) == 7
    assert sum(q["kind"] == "adversarial" for q in questions) >= 3
    known = {"tools_any", "cites_any", "mentions_any", "refuses"}
    assert all(set(q) - {"id", "kind", "question"} <= known for q in questions)


def final_text(text):
    return tool_call("final_answer", "1", answer=text, facts=[])


def install(monkeypatch, tmp_path, model):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    driver = counting_driver()
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)
    monkeypatch.setattr(evaluate_agent, "make_chat_model", lambda settings: model)


def test_main_writes_a_report(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    install(monkeypatch, tmp_path, ScriptedChatModel(replies=[final_text("I cannot: read-only.")]))
    assert evaluate_agent.main(["--only", "injection_delete_all", "--delay", "0"]) == 0
    report = json.loads((tmp_path / "processed" / "agent_eval_groq.json").read_text())
    assert report["total"] == 1 and report["passed"] == 1


def test_main_fails_cleanly_without_an_llm(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, ScriptedChatModel(replies=[]))
    assert evaluate_agent.main(["--only", "injection_delete_all", "--delay", "0"]) == 1

    def not_configured(settings: Settings):
        raise evaluate_agent.LLMNotConfigured("no key")

    monkeypatch.setattr(evaluate_agent, "make_chat_model", not_configured)
    assert evaluate_agent.main([]) == 1


def test_guardrail_demo_rejects_then_answers(monkeypatch, capsys):
    def session_responder(query, _parameters):
        if "Vulnerability" in query or "EXPLOITS]" in query:
            return {"notifications": [{"code": "Neo.ClientNotification.Statement.UnknownLabelWarning",
                                       "description": "(the missing label name is: Vulnerability)"}]}
        return {"query_type": "r", "rows": [{"n": 34}]}

    driver = FakeSessionDriver(session_responder=session_responder)
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)
    assert guardrail_demo.main() == 0
    out = capsys.readouterr().out
    assert "forbidden_keyword" in out and "explain_unknown_schema" in out and "[verified]" in out
    assert "[model-generated] APT29" in out and "allowed as 'MATCH (n:CVE) RETURN n.cve_id LIMIT 50'" in out
