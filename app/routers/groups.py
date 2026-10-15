"""Group endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import GROUP_ID_PATTERN, ErrorResponse
from app.models.groups import GroupTechniquesResponse
from app.services.groups import group_techniques

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get(
    "/{group_id}/techniques",
    response_model=GroupTechniquesResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No group with this ATT&CK id"}},
)
def get_group_techniques(
    group_id: Annotated[str, Path(pattern=GROUP_ID_PATTERN, description="ATT&CK group id, e.g. G0016")],
    driver: Annotated[Driver, Depends(get_driver)],
) -> GroupTechniquesResponse:
    """Question 1: the techniques a group uses, their tactics, mitigations and cited procedures."""
    result = group_techniques(driver, group_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {group_id} not found")
    return result
