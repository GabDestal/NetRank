"""Schemas for group endpoints (question 1)."""

from pydantic import BaseModel

from app.models.common import AttackRef


class GroupSummary(BaseModel):
    """A threat group."""

    attack_id: str
    name: str
    aliases: list[str] = []


class GroupTechnique(BaseModel):
    """One technique a group uses, where it sits in the kill chain, and what mitigates it."""

    attack_id: str
    name: str
    is_subtechnique: bool
    tactics: list[str]
    mitigations: list[AttackRef]
    procedure: str = ""
    references: list[str] = []


class GroupTechniquesResponse(BaseModel):
    """Body of GET /groups/{group_id}/techniques."""

    group: GroupSummary
    technique_count: int
    techniques: list[GroupTechnique]
