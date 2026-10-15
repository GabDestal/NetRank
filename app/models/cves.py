"""Schemas for CVE endpoints (question 3)."""

from typing import Literal

from pydantic import BaseModel

from app.models.common import CveSummary

MappingType = Literal["EXPLOITS_VIA", "PRIMARY_IMPACT", "SECONDARY_IMPACT"]


class MappedTechnique(BaseModel):
    """A technique CTID maps the CVE to, and how."""

    attack_id: str
    name: str
    mapping_type: MappingType


class AssociatedGroup(BaseModel):
    """A group that uses at least one technique the CVE enables."""

    attack_id: str
    name: str
    shared_techniques: list[str]


class SuggestedTechnique(BaseModel):
    """A technique suggested by the link prediction model (D18). Never a verified mapping."""

    attack_id: str
    name: str
    confidence: float
    model: str
    model_version: str
    top_features: list[str] = []
    rationale: str = ""


class CveGroupsResponse(BaseModel):
    """Body of GET /cves/{cve_id}/groups.

    `techniques` and `groups` come only from verified CTID mappings. Model output is kept apart in
    `suggested_techniques` and is never used to find groups.
    """

    cve: CveSummary
    association: Literal["shared_technique"] = "shared_technique"
    note: str
    techniques: list[MappedTechnique]
    group_count: int
    groups: list[AssociatedGroup]
    suggested_techniques: list[SuggestedTechnique] = []
    suggestions_label: Literal["model-generated, not verified"] = "model-generated, not verified"
    suggestions_status: str | None = None
