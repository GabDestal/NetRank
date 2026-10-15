"""Technique endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import TECHNIQUE_ID_PATTERN, ErrorResponse
from app.models.techniques import TechniqueCvesResponse
from app.services.techniques import technique_cves

router = APIRouter(prefix="/techniques", tags=["techniques"])


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
