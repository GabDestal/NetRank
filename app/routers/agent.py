"""Agent endpoints (D19): ask a question in natural language, or check a Cypher query against the guardrails."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.language_models import BaseChatModel
from neo4j import Driver

from app.agent.graph import Agent, LLMUnavailable
from app.agent.guardrails import GuardrailError, check_cypher, explain
from app.agent.llm import LLMNotConfigured, make_chat_model
from app.config import Settings, load_settings
from app.database.connection import get_driver
from app.models.agent import AgentResponse, AskRequest, CypherCheckRequest, CypherCheckResponse
from app.models.common import ErrorResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@lru_cache(maxsize=1)
def get_llm_settings() -> Settings:
    """Settings read once per process."""
    return load_settings()


def get_chat_model(settings: Annotated[Settings, Depends(get_llm_settings)]) -> BaseChatModel:
    """The configured chat model, or 503 if the LLM settings are incomplete."""
    try:
        return make_chat_model(settings)
    except LLMNotConfigured as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"LLM is not configured: {error}") from error


@router.post(
    "/ask",
    response_model=AgentResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                     "description": "LLM or Neo4j unavailable or not configured"}},
)
def ask(
    request: AskRequest,
    driver: Annotated[Driver, Depends(get_driver)],
    model: Annotated[BaseChatModel, Depends(get_chat_model)],
    settings: Annotated[Settings, Depends(get_llm_settings)],
) -> AgentResponse:
    """Answer a question with graph tools. Returns the tool calls, citations and each fact's provenance."""
    try:
        agent = Agent(model, driver, max_retries=settings.llm_max_retries)
        return agent.ask(request.question, provider=settings.llm_provider, model_name=settings.llm_model)
    except LLMUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"LLM is unavailable: {error}") from error


@router.post("/check-cypher", response_model=CypherCheckResponse)
def check(request: CypherCheckRequest, driver: Annotated[Driver, Depends(get_driver)]) -> CypherCheckResponse:
    """Run a query through the guardrails (static checks, then EXPLAIN) without executing it.

    A rejection is a normal answer (200 with allowed=false): the endpoint exists to show what is refused and why.
    """
    try:
        checked = check_cypher(request.query)
        explain(driver, checked)
    except GuardrailError as error:
        return CypherCheckResponse(allowed=False, rule=error.rule, reason=error.reason)
    return CypherCheckResponse(allowed=True, query=checked)
