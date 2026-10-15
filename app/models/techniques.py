"""Schemas for technique endpoints (question 2)."""

from datetime import date

from pydantic import BaseModel

from app.models.common import AttackRef, CveSummary


class TechniqueCve(CveSummary):
    """A KEV CVE that CTID maps to the technique as its exploitation technique."""

    date_added: date | None = None
    mapped_technique: str
    mapping_comment: str = ""


class TechniqueCvesResponse(BaseModel):
    """Body of GET /techniques/{technique_id}/cves."""

    technique: AttackRef
    include_subtechniques: bool
    cve_count: int
    cves: list[TechniqueCve]
