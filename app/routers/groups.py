"""Group endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.analytics import SimilarGroupsResponse
from app.models.common import GROUP_ID_PATTERN, ErrorResponse
from app.models.groups import GroupTechniquesResponse
from app.services.analytics import similar_groups
from app.services.groups import group_techniques

router = APIRouter(prefix="/groups", tags=["groups"])

GroupId = Annotated[str, Path(pattern=GROUP_ID_PATTERN, description="ATT&CK group id, e.g. G0016")]


@router.get(
    "/{group_id}/similar",
    response_model=SimilarGroupsResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No group with this ATT&CK id"}},
)
def get_similar_groups(
    group_id: GroupId,
    driver: Annotated[Driver, Depends(get_driver)],
    limit: Annotated[int, Query(ge=1, le=50, description="Similar groups returned")] = 10,
) -> SimilarGroupsResponse:
    """Groups with the most similar technique profiles, by GDS node similarity (Jaccard) run live (D17)."""
    result = similar_groups(driver, group_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {group_id} not found")
    return result


@router.get(
    "/{group_id}/techniques",
    response_model=GroupTechniquesResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No group with this ATT&CK id"}},
)
def get_group_techniques(
    group_id: GroupId,
    driver: Annotated[Driver, Depends(get_driver)],
) -> GroupTechniquesResponse:
    """Question 1: the techniques a group uses, their tactics, mitigations and cited procedures."""
    result = group_techniques(driver, group_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {group_id} not found")
    return result
