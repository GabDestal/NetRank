"""Schemas and identifier patterns shared by several endpoints."""

from pydantic import BaseModel

# Identifier formats, checked on input so a malformed id is a 422 before any query runs.
GROUP_ID_PATTERN = r"^G\d{4}$"
TECHNIQUE_ID_PATTERN = r"^T\d{4}(\.\d{3})?$"
CVE_ID_PATTERN = r"^CVE-\d{4}-\d{4,}$"

# Groups are linked to CVEs only through shared techniques (D12): this text travels with every such answer.
SHARED_TECHNIQUE_NOTE = (
    "Groups are listed because they use a technique this vulnerability enables (CTID mapping). "
    "This is an association through a shared technique, not evidence that the group exploited the vulnerability."
)


class ErrorResponse(BaseModel):
    """Body of every 404 and 503 response."""

    detail: str


class AttackRef(BaseModel):
    """A pointer to an ATT&CK object by its ATT&CK id and name."""

    attack_id: str
    name: str


class CveSummary(BaseModel):
    """The CVE fields most answers need."""

    cve_id: str
    name: str | None = None
    cvss_score: float | None = None
    cvss_source_type: str | None = None
    known_ransomware_use: bool | None = None
