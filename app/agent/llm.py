"""The agent's LLM: Groq, configured from the environment, with retry and backoff (decision log D66)."""

import groq
from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from app.agent.tools import tool_specs
from app.config import Settings
from app.errors import GdsUnavailableError

# Retried with exponential backoff and jitter: free-tier rate limits and transient server errors.
RETRYABLE = (groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError)


class AgentUnavailableError(GdsUnavailableError):
    """No LLM configured, or the provider kept failing (HTTP 503)."""


def build_llm(settings: Settings) -> Runnable:
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
    return model.bind_tools(tool_specs(), tool_choice="required").with_retry(
        retry_if_exception_type=RETRYABLE, wait_exponential_jitter=True, stop_after_attempt=settings.llm_max_attempts
    )
