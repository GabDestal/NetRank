"""The agent's LLM: Groq, configured from the environment, with counted retry and backoff (decision log D66)."""

import logging
import random
import re
import time
from typing import Any

import groq
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq

from app.agent.tools import tool_specs
from app.config import Settings
from app.errors import GdsUnavailableError

# Retried with exponential backoff and jitter: free-tier rate limits and transient server errors.
RETRYABLE = (groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError)
# Never retried: the configuration is wrong (retired model, bad key) and retrying cannot help.
CONFIGURATION = (groq.NotFoundError, groq.AuthenticationError, groq.PermissionDeniedError)
BASE_DELAY, MAX_DELAY = 2.0, 60.0
DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
# Groq names the exhausted limit in the 429 message, e.g. "on tokens per day (TPD): Limit 200000, ...".
# Account identifiers in provider messages are not secrets, but are not needed in logs or reports.
ORGANIZATION = re.compile(r"org_[A-Za-z0-9]+")
DAILY_LIMIT = re.compile(r"per day|\((?:TPD|RPD)\)", re.IGNORECASE)

log = logging.getLogger(__name__)


def parse_duration(text: str) -> float | None:
    """Seconds from Groq's reset headers: '585ms', '7.66s', '1m2.3s', '3h18m43.2s' (None if unparseable)."""
    parts = DURATION_PART.findall(text or "")
    if not parts:
        return None
    unit_seconds = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(value) * unit_seconds[unit] for value, unit in parts)


def server_wait(exc: Exception) -> float | None:
    """How long the provider asks us to wait before the token window allows another request."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = response.headers
    if (retry_after := headers.get("retry-after")) and retry_after.replace(".", "", 1).isdigit():
        return float(retry_after)
    return parse_duration(headers.get("x-ratelimit-reset-tokens", ""))


class AgentUnavailableError(GdsUnavailableError):
    """No LLM configured, or the provider kept failing (HTTP 503)."""


class LLMConfigurationError(AgentUnavailableError):
    """The provider rejected the model or the key (e.g. a retired Groq model)."""


class DailyQuotaError(AgentUnavailableError):
    """A per-day limit (tokens or requests) is exhausted: retrying within minutes cannot help."""


class ToolCallRejectedError(Exception):
    """The provider rejected the model's tool call because its arguments did not match the schema.

    `generation` is the model's full failed output (Groq's failed_generation), kept so a well-formed
    answer sent to a non-existent tool can be recovered (decision log D71).
    """

    def __init__(self, message: str, generation: str = "") -> None:
        """Message for the model and the trace, plus the raw failed output."""
        super().__init__(message)
        self.generation = generation


def rate_limit_details(exc: Exception) -> dict:
    """The 429 message and Groq's rate-limit headers, as logged and kept in evaluation rows."""
    response = getattr(exc, "response", None)
    headers = response.headers if response is not None else {}
    kept = {k: v for k, v in headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
    return {"message": ORGANIZATION.sub("org_<redacted>", str(getattr(exc, "message", exc))), "headers": kept}


def failed_generation(exc: groq.BadRequestError) -> str:
    """The model's full failed output from a 400 body, if any."""
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    return str(error.get("failed_generation", "")) if isinstance(error, dict) else ""


def rejected_tool_call(exc: groq.BadRequestError) -> str | None:
    """Message for a 400 caused by the model's own output (invalid tool call or unparseable output).

    Groq reports these with code 'tool_use_failed' and/or a 'failed_generation' field; the start of the
    failed generation is kept so the model (and the trace) can see what was wrong.
    """
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    if not isinstance(error, dict):
        return None
    if error.get("code") != "tool_use_failed" and "failed_generation" not in error:
        return None
    message = str(error.get("message", "tool call did not match its schema"))[:400]
    generation = str(error.get("failed_generation", ""))[:300]
    return f"{message} | model output: {generation}" if generation else message


class RetryingLLM:
    """Calls the model, retrying retryable errors with backoff, and counts what happened.

    `rate_limited` counts 429 responses and `retries` all retries, so an evaluation can report how
    many questions were throttled instead of hiding it.
    """

    def __init__(self, llm: Any, max_attempts: int, sleep=time.sleep) -> None:
        """`llm` is the bound chat model; `sleep` is injectable for tests."""
        self.llm = llm
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.retries = 0
        self.rate_limited = 0
        self.last_rate_limit: dict | None = None
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def invoke(self, messages: list) -> AIMessage:
        """One model turn; raises AgentUnavailableError once every attempt failed."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                message = self.llm.invoke(messages)
                usage = getattr(message, "usage_metadata", None) or {}
                self.prompt_tokens += usage.get("input_tokens", 0)
                self.completion_tokens += usage.get("output_tokens", 0)
                return message
            except groq.BadRequestError as exc:
                if message := rejected_tool_call(exc):
                    raise ToolCallRejectedError(message, failed_generation(exc)) from exc
                raise
            except CONFIGURATION as exc:
                raise LLMConfigurationError(
                    f"LLM configuration rejected by the provider ({type(exc).__name__}): "
                    + "check GROQ_MODEL and GROQ_API_KEY"
                ) from exc
            except RETRYABLE as exc:
                if isinstance(exc, groq.RateLimitError):
                    self.rate_limited += 1
                    self.last_rate_limit = rate_limit_details(exc)
                    log.warning(f"Groq 429 (attempt {attempt}): {self.last_rate_limit['message']} "
                                + f"headers={self.last_rate_limit['headers']}")
                    if DAILY_LIMIT.search(self.last_rate_limit["message"]):
                        message = self.last_rate_limit["message"][:300]
                        raise DailyQuotaError(f"Groq daily limit reached: {message}") from exc
                if attempt == self.max_attempts:
                    raise AgentUnavailableError(
                        f"LLM provider failed after {attempt} attempts ({type(exc).__name__})"
                    ) from exc
                self.retries += 1
                backoff = BASE_DELAY * 2 ** (attempt - 1) * (0.5 + random.random() / 2)
                # Wait for the provider's own reset time when it gives one (per-minute token windows).
                self.sleep(min(MAX_DELAY, max(backoff, (server_wait(exc) or 0.0) + 0.5)))
        raise AssertionError("unreachable")


def build_llm(settings: Settings) -> RetryingLLM:
    """Chat model with every tool bound; a tool call is required on every turn.

    Requiring a tool call means the final answer always arrives through submit_answer, i.e. as
    structured data validated by Pydantic, never as free text.
    """
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        raise AgentUnavailableError("The agent is disabled: set GROQ_API_KEY (and optionally GROQ_MODEL)")
    model = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key.get_secret_value(),
        temperature=0,
        max_retries=0,
        timeout=60,
    )
    return RetryingLLM(model.bind_tools(tool_specs(), tool_choice="required"), settings.llm_max_attempts)
