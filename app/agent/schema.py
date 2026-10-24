"""Structured agent output: tagged claims, the tool-call trace, and the API request/response."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

Tag = Literal["verified", "predicted", "interpreted"]
# incomplete = the results answer part of the question: claims say what was found, `missing` what was not (D78).
Kind = Literal["answer", "incomplete", "clarification", "refusal", "failure"]


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
    missing: list[str] = Field(default_factory=list, description="Set when kind = incomplete: what is still unknown.")
    candidates: list[Candidate] = Field(default_factory=list, description="Set when kind = clarification.")


class DraftClaim(BaseModel):
    """What the LLM writes for one claim (the verifier adds provenance and downgrade fields)."""

    # The live runs showed gpt-oss-120b naming these fields inconsistently: "type" or "tag", and
    # "text", "statement" or "claim". Every observed spelling is accepted and merged below; a claim
    # still needs one statement and one type (decision log D65). The alternatives are left out of
    # the JSON schema the model sees (fewer tokens per turn); the API response uses text and tag.
    text: str | None = Field(default=None, max_length=600, description="One short statement.")
    statement: SkipJsonSchema[str | None] = Field(default=None, max_length=600)
    claim: SkipJsonSchema[str | None] = Field(default=None, max_length=600)
    type: Tag | None = None
    tag: SkipJsonSchema[Tag | None] = None
    sources: list[str] = Field(default_factory=list, description="Tool call ids, e.g. 't2'.")
    matchIds: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def merge_spellings(self) -> "DraftClaim":
        """Require one statement and one tag, whichever spelling the model used."""
        self.text = self.text or self.statement or self.claim
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
    missing: list[str] = Field(default_factory=list, description="Only for kind = incomplete: what is still unknown.")
    candidates: list[Candidate] = Field(default_factory=list, description="Only for kind = clarification.")

    @model_validator(mode="after")
    def incomplete_names_what_is_missing(self) -> "DraftAnswer":
        """An incomplete answer must say what it could not find."""
        if self.kind == "incomplete" and not self.missing:
            raise ValueError("kind incomplete needs 'missing': what the tool results did not show")
        return self

    def to_answer(self) -> AgentAnswer:
        """The response answer."""
        return AgentAnswer(
            kind=self.kind,
            summary=self.summary,
            claims=[c.to_claim() for c in self.claims],
            missing=self.missing,
            candidates=self.candidates,
        )

    @classmethod
    def unknown_fields(cls, data: dict) -> list[str]:
        """Keys of a payload that are not submit_answer fields (used before accepting a misrouted answer)."""
        nested = {"claims": DraftClaim, "candidates": Candidate}
        unknown = [key for key in data if key not in set(cls.model_fields.keys())]
        for key, model in nested.items():
            items = data.get(key) if isinstance(data.get(key), list) else []
            unknown += [
                f"{key}.{field}"
                for item in items
                if isinstance(item, dict)
                for field in item
                if field not in set(model.model_fields.keys())
            ]
        return unknown


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
    recoveredCalls: int = Field(
        default=0, description="Rejected calls whose payload was a valid answer sent to a non-existent tool."
    )
    downgradedClaims: int
    model: str
