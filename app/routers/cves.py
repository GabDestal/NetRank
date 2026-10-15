"""CVE endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import CVE_ID_PATTERN, ErrorResponse
from app.models.cves import CveGroupsResponse
from app.services.cves import cve_groups

router = APIRouter(prefix="/cves", tags=["cves"])


@router.get(
    "/{cve_id}/groups",
    response_model=CveGroupsResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "CVE not in the KEV catalog"}},
)
def get_cve_groups(
    cve_id: Annotated[str, Path(pattern=CVE_ID_PATTERN, description="CVE id, e.g. CVE-2021-44228")],
    driver: Annotated[Driver, Depends(get_driver)],
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum groups returned")] = 25,
) -> CveGroupsResponse:
    """Question 3: groups that use a technique this CVE enables. An association, not attribution."""
    result = cve_groups(driver, cve_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{cve_id} is not in the KEV catalog")
    return result
