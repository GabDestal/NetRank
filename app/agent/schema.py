"""Structured agent output: tagged claims, the tool-call trace, and the API request/response."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class DraftClaim(BaseModel):
    """What the LLM writes for one claim (the verifier adds provenance and downgrade fields)."""

    # The live runs showed gpt-oss-120b naming these fields inconsistently ("type" or "tag",
    # "text" or "statement"), and Groq rejects a call whose arguments miss a required property
    # before we ever see it. Both spellings are therefore accepted and merged below; a claim
    # still needs one of each (decision log D65). The API response always uses text and tag.
    text: str | None = Field(default=None, max_length=600, description="One short factual statement.")
    statement: str | None = Field(default=None, max_length=600, description="Same as text (either is accepted).")
    type: Tag | None = Field(
        default=None, description="verified (tool result), predicted (predict_match), interpreted."
    )
    tag: Tag | None = Field(default=None, description="Same as type (either is accepted).")
    sources: list[str] = Field(default_factory=list, description="Tool call ids like 't2' (strings only).")
    matchIds: list[str] = Field(default_factory=list, description="Match ids from the cited results, if any.")

    @model_validator(mode="after")
    def merge_spellings(self) -> "DraftClaim":
        """Require one statement and one tag, whichever spelling the model used."""
        self.text = self.text or self.statement
        self.type = self.type or self.tag
        if not self.text or not self.type:
            raise ValueError("each claim needs a statement (text) and a type (verified/predicted/interpreted)")
        return self

    def to_claim(self) -> Claim:
        """The response claim."""
        return Claim(text=self.text, tag=self.type, sources=self.sources, matchIds=self.matchIds)


class DraftAnswer(BaseModel):
    """submit_answer arguments: the LLM-facing answer schema, kept minimal on purpose."""

    kind: Kind
    summary: str = Field(min_length=1, max_length=1500)
    claims: list[DraftClaim] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list, description="Only for kind = clarification.")

    def to_answer(self) -> AgentAnswer:
        """The response answer."""
        return AgentAnswer(kind=self.kind, summary=self.summary, claims=[c.to_claim() for c in self.claims],
                           candidates=self.candidates)


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
    invalidToolCalls: int = Field(description="Model tool calls rejected for not matching their schema.")
    downgradedClaims: int
    model: str
