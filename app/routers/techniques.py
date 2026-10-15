"""Technique endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.analytics import CentralTechniquesResponse
from app.models.common import TECHNIQUE_ID_PATTERN, ErrorResponse
from app.models.techniques import TechniqueCvesResponse
from app.services.analytics import central_techniques
from app.services.techniques import technique_cves

router = APIRouter(prefix="/techniques", tags=["techniques"])


@router.get(
    "/central",
    response_model=CentralTechniquesResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                     "description": "Analytics not computed yet"}},
)
def get_central_techniques(
    driver: Annotated[Driver, Depends(get_driver)],
    by: Annotated[Literal["used_by_groups", "betweenness"],
                  Query(description="used_by_groups = most used; betweenness = connectors between toolkits")]
    = "used_by_groups",
    limit: Annotated[int, Query(ge=1, le=200, description="Techniques returned")] = 20,
    community_limit: Annotated[int, Query(ge=0, le=50, description="Communities returned")] = 6,
) -> CentralTechniquesResponse:
    """Question 6: technique centrality (degree, betweenness) and communities, computed by GDS in make analytics."""
    result = central_techniques(driver, by=by, limit=limit, community_limit=community_limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Analytics have not been computed: run make analytics")
    return result


@router.get(
    "/{technique_id}/cves",
    response_model=TechniqueCvesResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No technique with this id"}},
)
def get_technique_cves(
    technique_id: Annotated[str, Path(pattern=TECHNIQUE_ID_PATTERN, description="ATT&CK id, e.g. T1190")],
    driver: Annotated[Driver, Depends(get_driver)],
    ransomware: Annotated[bool | None, Query(description="Only CVEs with (true) or without (false) "
                                                          "known ransomware use")] = None,
    include_subtechniques: Annotated[bool, Query(description="Also include CVEs mapped to its "
                                                             "sub-techniques")] = True,
) -> TechniqueCvesResponse:
    """Question 2: KEV CVEs that CTID maps to this technique as their exploitation technique."""
    result = technique_cves(driver, technique_id, ransomware=ransomware, include_subtechniques=include_subtechniques)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Technique {technique_id} not found")
    return result
