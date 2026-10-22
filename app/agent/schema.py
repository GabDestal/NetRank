"""Structured agent output: tagged claims, the tool-call trace, and the API request/response."""

from typing import Literal

from pydantic import BaseModel, Field

Tag = Literal["verified", "predicted", "interpreted"]
Kind = Literal["answer", "clarification", "refusal", "failure"]


class Claim(BaseModel):
    """One statement of the answer and where it comes from (decision log D64).

    verified    = read from the graph by a tool (every number must appear in a cited tool result);
    predicted   = produced by the match-outcome model (must cite predict_match);
    interpreted = the LLM's own reading or wording, not directly checkable.
    """

    text: str = Field(min_length=1, max_length=600)
    tag: Tag
    sources: list[str] = Field(default_factory=list, description="Tool call ids (t1, t2...) the claim relies on.")
    matchIds: list[str] = Field(default_factory=list, description="Match ids that support the claim.")
    cypher: str | None = Field(default=None, description="Filled in when a cited source ran fallback Cypher.")
    downgradedFrom: Tag | None = Field(default=None, description="Original tag when the verifier downgraded it.")
    downgradeReason: str | None = None


class Candidate(BaseModel):
    """A player the user may have meant."""

    id: int
    name: str
    ioc: str | None = None


class AgentAnswer(BaseModel):
    """What the agent concluded."""

    kind: Kind
    summary: str = Field(min_length=1, max_length=1500)
    claims: list[Claim] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list, description="Set when kind = clarification.")


class ToolCallRecord(BaseModel):
    """One executed (or rejected) tool call, exposed in the response."""

    id: str
    tool: str
    arguments: dict
    success: bool
    result: dict | list | None = None
    error: str | None = None
    guardrail: str | None = Field(default=None, description="Guardrail layer that rejected the call, if any.")


class AskRequest(BaseModel):
    """POST /api/agent/ask body."""

    question: str = Field(min_length=3, max_length=500)


class AgentResponse(BaseModel):
    """Answer, full trace and the counters the evaluation reports."""

    question: str
    answer: AgentAnswer
    trace: list[ToolCallRecord]
    steps: int
    fallbackCypherCalls: int
    guardrailRejections: int
    downgradedClaims: int
    model: str
