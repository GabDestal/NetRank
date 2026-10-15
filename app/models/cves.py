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


class CveGroupsResponse(BaseModel):
    """Body of GET /cves/{cve_id}/groups."""

    cve: CveSummary
    association: Literal["shared_technique"] = "shared_technique"
    note: str
    techniques: list[MappedTechnique]
    group_count: int
    groups: list[AssociatedGroup]
