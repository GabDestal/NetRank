"""POST /api/agent/ask."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent import graph
from app.agent.llm import build_llm
from app.agent.schema import AgentResponse, AskRequest
from app.config import get_settings
from app.database.client import Neo4jClient, get_db
from app.models.common import error_responses

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/ask", response_model=AgentResponse, responses=error_responses(503))
def ask(body: AskRequest, db: Annotated[Neo4jClient, Depends(get_db)]) -> AgentResponse:
    """Answer a tennis question with tools; every claim is tagged verified / predicted / interpreted.

    The response carries the full tool-call trace, the number of fallback Cypher calls and guardrail
    rejections, and how many claims the verifier downgraded. Betting advice is always refused.
    """
    settings = get_settings()
    return graph.ask(db, build_llm(settings), body.question, settings.agent_max_steps, settings.groq_model)
