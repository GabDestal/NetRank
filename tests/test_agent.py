"""Tests for the agent (D19): LLM factory and backoff, the LangGraph loop, fact tagging and the endpoints."""
# pylint: disable=missing-function-docstring

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent import graph, llm
from app.agent.graph import Agent, FactArgs, LLMUnavailable, mentioned_ids, tag_facts
from app.agent.llm import LLMNotConfigured, invoke_with_backoff, is_invalid_tool_call, is_rate_limited, make_chat_model
from app.agent.scripted import ScriptedChatModel, tool_call
from app.config import Settings
from app.database.connection import get_driver
from app.main import app
from app.routers import agent as agent_router
from app.services import cves
from tests.fakes import FakeSessionDriver
from tests.test_api import CVE_RECORD

client = TestClient(app)


class HttpError(Exception):
    """An SDK-style error carrying an HTTP response."""

    def __init__(self, status, text="", headers=None):
        super().__init__(text)
        self.response = httpx.Response(status, headers=headers or {})


def settings(**overrides):
    values = {"log_level": "INFO", "data_dir": "data", "llm_provider": "groq", "llm_model": "qwen/qwen3.8-27b",
              "groq_api_key": "gsk-test"} | overrides
    return Settings(**values)


@pytest.mark.parametrize("provider, key_field, class_name", [
    ("groq", "groq_api_key", "ChatGroq"),
    ("anthropic", "anthropic_api_key", "ChatAnthropic"),
    ("ollama", None, "ChatOllama"),
])
def test_factory_builds_each_provider(provider, key_field, class_name):
    overrides = {"llm_provider": provider} | ({key_field: "secret-key"} if key_field else {})
    assert type(make_chat_model(settings(**overrides))).__name__ == class_name


@pytest.mark.parametrize("overrides, message", [
    ({"groq_api_key": ""}, "GROQ_API_KEY"),
    ({"llm_provider": "anthropic"}, "ANTHROPIC_API_KEY"),
    ({"llm_provider": "openai"}, "Unknown LLM_PROVIDER"),
])
def test_factory_refuses_incomplete_settings(overrides, message):
    with pytest.raises(LLMNotConfigured, match=message):
        make_chat_model(settings(**overrides))


def test_keys_never_appear_in_settings_repr():
    assert "gsk-test" not in repr(settings())


class FlakyModel:
    """Fails with the given errors, then answers."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return AIMessage(content="ok")


def test_backoff_retries_429_with_growing_waits_and_retry_after():
    waits = []
    model = FlakyModel([HttpError(429), HttpError(429, headers={"retry-after": "30"}), HttpError(429)])
    assert invoke_with_backoff(model, [], max_retries=3, sleep=waits.append).content == "ok"
    assert model.calls == 4
    assert 2 <= waits[0] < 3 and 30 <= waits[1] < 31 and 8 <= waits[2] < 9


def test_backoff_gives_up_after_max_retries_and_never_retries_other_errors():
    with pytest.raises(HttpError):
        invoke_with_backoff(FlakyModel([HttpError(429)] * 3), [], max_retries=2, sleep=lambda s: None)
    model = FlakyModel([HttpError(401)])
    with pytest.raises(HttpError):
        invoke_with_backoff(model, [], sleep=lambda s: None)
    assert model.calls == 1


def test_error_classification():
    assert is_rate_limited(HttpError(429)) and not is_rate_limited(HttpError(500))
    assert is_invalid_tool_call(HttpError(400, "code: tool_use_failed"))
    assert not is_invalid_tool_call(HttpError(400, "bad request"))
    assert llm.retry_after(HttpError(429, headers={"retry-after": "soon"})) is None


def facts(*pairs):
    return [FactArgs(statement=s, citations=c) for s, c in pairs]


CALLS = [{"returned_ids": ["T1190", "fortinet:fortios"], "model_generated_ids": ["T1059"]}]


def test_provenance_is_decided_by_the_server_from_citations():
    tagged = tag_facts(facts(("a", ["t1190", "FORTINET:FORTIOS"]), ("b", ["T1059"]), ("c", ["G0016"]), ("d", [])),
                       CALLS)
    assert [f.provenance for f in tagged] == ["verified", "model-generated", "model-generated", "model-generated"]
    assert tagged[0].citations == ["T1190", "fortinet:fortios"]
    assert "D18" in tagged[1].note and "G0016" in tagged[2].note and tagged[3].note == "no citation"


def test_mentioned_ids_matches_whole_ids_only():
    ids = {"T1078", "T1078.004", "M1026", "fortinet:fortios"}
    assert mentioned_ids("Use M1026 against T1078.004 on fortinet:fortios.", ids) == \
        ["M1026", "T1078.004", "fortinet:fortios"]


def neo4j_for_tools():
    """Answers the cve_groups tool queries and the guarded Cypher sessions."""
    def responder(query, _parameters):
        if query == cves.SUGGESTIONS_QUERY:
            return [{"status": "not stored", "suggestions": []}]
        return [CVE_RECORD] if query == cves.CVE_GROUPS_QUERY else []

    return FakeSessionDriver(responder, lambda query, parameters: {"rows": [{"n": 34}]})


def run(replies, question="q"):
    model = ScriptedChatModel(replies=replies)
    return Agent(model, neo4j_for_tools()).ask(question, provider="scripted", model_name="test"), model


def test_agent_runs_tools_and_answers_with_tagged_facts():
    response, model = run([
        tool_call("cve_groups", "1", cve_id="CVE-2021-44228"),
        tool_call("final_answer", "2", answer="Sandworm is associated through T1190.",
                  facts=[{"statement": "CVE-2021-44228 maps to T1190", "citations": ["CVE-2021-44228", "T1190"]}]),
    ])
    assert response.stopped == "answered" and response.facts[0].provenance == "verified"
    assert response.citations == ["CVE-2021-44228", "T1190"]
    call = response.tool_calls[0]
    assert call.status == "ok" and "G0034" in call.returned_ids and "INFERRED_MAPS_TO" in call.path
    tool_result = model.seen[1][-1]
    assert tool_result.type == "tool" and "Sandworm Team" in tool_result.content
    assert model.seen[0][0].content == graph.SYSTEM_PROMPT


def test_rejected_cypher_is_fed_back_and_the_retry_budget_is_enforced():
    bad = "MATCH (n) DETACH DELETE n"
    replies = [tool_call("run_cypher", str(i), query=bad) for i in range(4)]
    response, model = run(replies + [AIMessage(content="I cannot change the graph.")])
    statuses = [(c.status, c.error) for c in response.tool_calls]
    assert [s for s, _ in statuses] == ["rejected"] * 4
    assert statuses[3][1] == "retry budget used up" and len(response.guardrail_events) == 3
    assert "2 retries left" in model.seen[1][-1].content and "No retries left" in model.seen[3][-1].content
    assert response.stopped == "no_final_answer" and response.answer == "I cannot change the graph."


def test_tool_errors_and_misplaced_final_answer_are_reported_back():
    response, _ = run([
        AIMessage(content="", tool_calls=[
            {"name": "group_techniques", "args": {"group_id": "APT29"}, "id": "1", "type": "tool_call"},
            {"name": "final_answer", "args": {"answer": "early"}, "id": "2", "type": "tool_call"}]),
        tool_call("final_answer", "3", answer="done", facts=[]),
    ])
    assert [c.status for c in response.tool_calls] == ["error", "error"]
    assert "group_id" in response.tool_calls[0].error and "alone" in response.tool_calls[1].error


def test_plain_text_answers_still_get_citations_from_returned_ids():
    response, _ = run([tool_call("cve_groups", "1", cve_id="CVE-2021-44228"),
                       AIMessage(content=[{"type": "text", "text": "T1190 links it to Sandworm (G0034)."}])])
    assert response.stopped == "no_final_answer" and response.facts == []
    assert response.citations == ["G0034", "T1190"]


def test_malformed_final_answer_keeps_the_text():
    response, _ = run([tool_call("final_answer", "1", answer="short", facts="not a list")])
    assert response.answer == "short" and response.stopped == "no_final_answer"


def test_step_limit_stops_the_loop(monkeypatch):
    monkeypatch.setattr(graph, "MAX_STEPS", 2)
    response, _ = run([tool_call("search_entities", str(i), text="apt") for i in range(3)])
    assert response.stopped == "step_limit" and len(response.tool_calls) == 2


class RejectingModel(ScriptedChatModel):
    """Raises a provider tool-call rejection a set number of times before replying."""

    failures: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.failures:
            self.failures -= 1
            raise HttpError(400, "Tool call validation failed: tool_use_failed")
        return super()._generate(messages, stop, run_manager, **kwargs)


def test_rejected_tool_calls_are_retried_with_the_error_then_give_up():
    model = RejectingModel(replies=[tool_call("final_answer", "1", answer="ok", facts=[])], failures=1)
    response = Agent(model, neo4j_for_tools()).ask("q", provider="p", model_name="m")
    assert response.answer == "ok" and "was rejected" in model.seen[-1][-1].content
    model = RejectingModel(replies=[], failures=5)
    with pytest.raises(LLMUnavailable):
        Agent(model, neo4j_for_tools()).ask("q", provider="p", model_name="m")


@pytest.fixture(name="api")
def fixture_api():
    def install(model=None, driver=None, llm_settings=None):
        app.dependency_overrides[get_driver] = lambda: driver or neo4j_for_tools()
        app.dependency_overrides[agent_router.get_llm_settings] = lambda: llm_settings or settings()
        if model is not None:
            app.dependency_overrides[agent_router.get_chat_model] = lambda: model

    yield install
    app.dependency_overrides.clear()


def test_ask_endpoint_returns_the_full_trace(api):
    api(model=ScriptedChatModel(replies=[tool_call("final_answer", "1", answer="none", facts=[])]))
    body = client.post("/agent/ask", json={"question": "Which groups use T1190?"}).json()
    assert body["answer"] == "none" and body["provider"] == "groq" and body["model"] == "qwen/qwen3.8-27b"
    assert {"facts", "citations", "tool_calls", "guardrail_events", "answer_label"} <= set(body)


def test_ask_endpoint_errors(api):
    api(llm_settings=settings(groq_api_key=""))
    response = client.post("/agent/ask", json={"question": "anything"})
    assert response.status_code == 503 and "GROQ_API_KEY" in response.json()["detail"]
    api(model=RejectingModel(replies=[], failures=5))
    assert client.post("/agent/ask", json={"question": "anything"}).status_code == 503
    assert client.post("/agent/ask", json={"question": "x"}).status_code == 422


def test_check_cypher_endpoint(api):
    api(driver=FakeSessionDriver(session_responder=lambda query, parameters: {"query_type": "r"}))
    allowed = client.post("/agent/check-cypher", json={"query": "MATCH (n:CVE) RETURN n.cve_id"}).json()
    assert allowed == {"allowed": True, "query": "MATCH (n:CVE) RETURN n.cve_id\nLIMIT 50", "rule": None,
                       "reason": None}
    rejected = client.post("/agent/check-cypher", json={"query": "MATCH (n) DETACH DELETE n"}).json()
    assert rejected["allowed"] is False and rejected["rule"] == "forbidden_keyword"


def test_llm_settings_are_loaded_once(monkeypatch):
    agent_router.get_llm_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "Ollama")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    try:
        loaded = agent_router.get_llm_settings()
        assert loaded.llm_provider == "ollama" and loaded.llm_model == "qwen2.5:3b"
        assert agent_router.get_llm_settings() is loaded
    finally:
        agent_router.get_llm_settings.cache_clear()
