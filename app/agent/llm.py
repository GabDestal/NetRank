"""Chat model factory and rate-limit handling (D19).

LLM_PROVIDER picks the model: groq (default, free tier), anthropic, or ollama (local, no key).
Free tiers answer HTTP 429 when the per-minute token budget is spent, so every LLM call goes through
invoke_with_backoff, which waits and retries instead of failing the question.
"""

import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.config import Settings

LOGGER = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0


class LLMNotConfigured(Exception):
    """The LLM settings cannot produce a model (unknown provider, missing key)."""


def make_chat_model(settings: Settings) -> BaseChatModel:
    """Build the chat model the settings ask for. Temperature 0 so answers are as repeatable as possible.

    The SDKs' own retries are turned off: invoke_with_backoff does it, the same way for every provider.
    Provider packages are imported only when chosen, so an unused provider's package is never loaded.
    """
    # pylint: disable=import-outside-toplevel
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise LLMNotConfigured("GROQ_API_KEY is not set (or set LLM_PROVIDER=ollama to use a local model)")
        from langchain_groq import ChatGroq
        return ChatGroq(model=settings.llm_model, api_key=settings.groq_api_key, temperature=0, max_tokens=2048,
                        timeout=60, max_retries=0)
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set (or set LLM_PROVIDER=ollama to use a local model)")
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=settings.llm_model, api_key=settings.anthropic_api_key, temperature=0,
                             max_tokens=2048, timeout=60, max_retries=0)
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama
        # The default 4k context is too small for the tool descriptions plus a few tool results.
        return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url, temperature=0, num_ctx=16384)
    raise LLMNotConfigured(f"Unknown LLM_PROVIDER {settings.llm_provider!r}: use groq, anthropic or ollama")


def is_rate_limited(error: Exception) -> bool:
    """True for HTTP 429 from any provider SDK (they raise different classes, all carrying the status code)."""
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    return status == 429 or type(error).__name__ == "RateLimitError"


def is_invalid_tool_call(error: Exception) -> bool:
    """True when the provider rejected a malformed tool call (Groq: HTTP 400, code tool_use_failed)."""
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    return status == 400 and ("tool_use_failed" in str(error) or "Tool call validation failed" in str(error))


def retry_after(error: Exception) -> float | None:
    """The server's Retry-After header in seconds, if it sent one."""
    headers = getattr(getattr(error, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def invoke_with_backoff(model: Any, messages: Sequence[BaseMessage], *, max_retries: int = 6,
                        sleep: Callable[[float], None] = time.sleep) -> BaseMessage:
    """Call the model, retrying on HTTP 429 with exponential backoff (2, 4, 8... s, capped at 60 s, plus jitter).

    Uses the server's Retry-After when it is longer. Any other error, or a 429 after max_retries
    retries, is raised to the caller.
    """
    for attempt in range(max_retries + 1):
        try:
            return model.invoke(list(messages))
        except Exception as error:  # pylint: disable=broad-exception-caught
            if not is_rate_limited(error) or attempt == max_retries:
                raise
            wait = min(BACKOFF_BASE_SECONDS * 2 ** attempt, BACKOFF_MAX_SECONDS)
            wait = max(wait, retry_after(error) or 0.0) + random.uniform(0, 1)
            LOGGER.warning("LLM rate limited (429), retry %d/%d in %.1f s", attempt + 1, max_retries, wait)
            sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover
