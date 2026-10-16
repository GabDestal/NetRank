"""Schemas for the agent endpoints (D19)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

ANSWER_LABEL = "written by the LLM from the tool results below; check each fact's provenance and citations"


class AskRequest(BaseModel):
    """Body of POST /agent/ask."""

    question: str = Field(min_length=3, max_length=500, description="A question about the threat graph")


class ToolCallRecord(BaseModel):
    """One tool call the agent made, with what it walked and what it returned."""

    step: int
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "error", "rejected"]
    path: str | None = None
    source: str | None = None
    cypher: str | None = Field(None, description="For run_cypher: the query that actually ran, LIMIT included")
    returned_ids: list[str] = []
    model_generated_ids: list[str] = []
    error: str | None = None


class Fact(BaseModel):
    """One claim from the answer. Provenance is set by the server from the citations, never by the LLM."""

    statement: str
    provenance: Literal["verified", "model-generated"]
    citations: list[str]
    note: str | None = None


class GuardrailEvent(BaseModel):
    """A generated query the guardrails rejected."""

    step: int
    rule: str
    reason: str
    query: str


class AgentResponse(BaseModel):
    """Body of POST /agent/ask."""

    question: str
    answer: str
    answer_label: str = ANSWER_LABEL
    facts: list[Fact]
    citations: list[str] = Field(description="Graph ids cited by the facts that a tool actually returned")
    tool_calls: list[ToolCallRecord]
    guardrail_events: list[GuardrailEvent]
    stopped: Literal["answered", "no_final_answer", "step_limit"]
    provider: str
    model: str


class CypherCheckRequest(BaseModel):
    """Body of POST /agent/check-cypher."""

    query: str = Field(min_length=1, max_length=5000)


class CypherCheckResponse(BaseModel):
    """Whether the guardrails accept a query. Nothing is executed, only EXPLAINed."""

    allowed: bool
    query: str | None = Field(None, description="The query as it would run, with LIMIT enforced")
    rule: str | None = None
    reason: str | None = None
