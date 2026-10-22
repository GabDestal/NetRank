"""Retry and backoff around the Groq model: retries are counted, never hidden."""

import groq
import httpx
import pytest
from langchain_core.messages import AIMessage

from app.agent.llm import (
    AgentUnavailableError,
    LLMConfigurationError,
    RetryingLLM,
    ToolCallRejectedError,
    build_llm,
    parse_duration,
    server_wait,
)
from app.config import Settings


def rate_limit() -> groq.RateLimitError:
    """A 429 as the Groq SDK raises it."""
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
    return groq.RateLimitError("rate limited", response=response, body=None)


class Flaky:
    """Raises the given errors, then answers."""

    def __init__(self, errors):
        """Errors to raise before succeeding."""
        self.errors = list(errors)

    def invoke(self, _messages):
        """Fail while errors remain."""
        if self.errors:
            raise self.errors.pop(0)
        return AIMessage(content="ok")


def test_rate_limits_are_retried_with_growing_delays_and_counted():
    """Two 429s, then success: two retries, two rate-limit events, increasing sleeps."""
    sleeps = []
    llm = RetryingLLM(Flaky([rate_limit(), rate_limit()]), max_attempts=5, sleep=sleeps.append)
    assert llm.invoke([]).content == "ok"
    assert (llm.retries, llm.rate_limited) == (2, 2)
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 0.9


def test_exhausted_retries_fail_cleanly():
    """After the last attempt the error surfaces as a 503-class AgentUnavailableError."""
    llm = RetryingLLM(Flaky([rate_limit()] * 3), max_attempts=3, sleep=lambda s: None)
    with pytest.raises(AgentUnavailableError, match="after 3 attempts"):
        llm.invoke([])
    assert llm.rate_limited == 3 and llm.retries == 2


def test_other_errors_are_not_retried():
    """A bug is not a rate limit: it propagates at once."""
    llm = RetryingLLM(Flaky([ValueError("bad request")]), max_attempts=5, sleep=lambda s: None)
    with pytest.raises(ValueError):
        llm.invoke([])
    assert llm.retries == 0


def test_build_llm_needs_a_key():
    """No key: the agent is disabled with an explicit message."""
    with pytest.raises(AgentUnavailableError, match="GROQ_API_KEY"):
        build_llm(Settings(groq_api_key=None))
    assert isinstance(build_llm(Settings(groq_api_key="gsk_test", groq_model="some-model")), RetryingLLM)


def test_retired_model_fails_fast_without_retries():
    """A 404 model_not_found is a configuration error: no retry, explicit message."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    missing = groq.NotFoundError("model_not_found", response=httpx.Response(404, request=request), body=None)
    llm = RetryingLLM(Flaky([missing]), max_attempts=5, sleep=lambda s: None)
    with pytest.raises(LLMConfigurationError, match="GROQ_MODEL"):
        llm.invoke([])
    assert llm.retries == 0


def test_tool_use_failed_becomes_a_rejection():
    """Groq's 400 tool_use_failed carries the validation message; other 400s propagate."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    body = {"error": {"code": "tool_use_failed", "message": "parameters for tool submit_answer did not match schema"}}
    rejected = groq.BadRequestError("bad", response=httpx.Response(400, request=request), body=body)
    with pytest.raises(ToolCallRejectedError, match="did not match schema"):
        RetryingLLM(Flaky([rejected]), max_attempts=3, sleep=lambda s: None).invoke([])
    other = groq.BadRequestError("bad", response=httpx.Response(400, request=request), body={"error": {"code": "x"}})
    with pytest.raises(groq.BadRequestError):
        RetryingLLM(Flaky([other]), max_attempts=3, sleep=lambda s: None).invoke([])


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("585ms", 0.585), ("7.66s", 7.66), ("1m2.3s", 62.3), ("3h18m43.2s", 11923.2), ("", None), ("soon", None)],
)
def test_reset_header_durations(text, seconds):
    """Groq's reset headers in seconds."""
    assert parse_duration(text) == (pytest.approx(seconds) if seconds is not None else None)


def test_rate_limit_waits_for_the_token_window():
    """The wait follows the provider's reset header (capped), not just the exponential backoff."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request, headers={"x-ratelimit-reset-tokens": "41.5s"})
    limited = groq.RateLimitError("tokens per minute", response=response, body=None)
    sleeps = []
    RetryingLLM(Flaky([limited]), max_attempts=3, sleep=sleeps.append).invoke([])
    assert sleeps == [pytest.approx(42.0)]
    retry_after = httpx.Response(429, request=request, headers={"retry-after": "12"})
    assert server_wait(groq.RateLimitError("x", response=retry_after, body=None)) == 12.0
