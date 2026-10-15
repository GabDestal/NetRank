"""Mitigation endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from neo4j import Driver

from app.database.connection import get_driver
from app.models.analytics import MitigationPlanResponse
from app.services.analytics import mitigation_plan

router = APIRouter(prefix="/mitigations", tags=["mitigations"])


@router.get("/plan", response_model=MitigationPlanResponse)
def get_mitigation_plan(
    driver: Annotated[Driver, Depends(get_driver)],
    since: Annotated[date | None, Query(description="Only CVEs added to KEV on or after this date")] = None,
    max_picks: Annotated[int | None, Query(ge=1, le=50, description="Stop after this many mitigations")] = None,
) -> MitigationPlanResponse:
    """Question 5: which mitigations would cover the most techniques reachable from exploited CVEs,
    as a greedy weighted cover (D14). Techniques no mitigation covers are listed, not hidden."""
    return mitigation_plan(driver, since=since, max_picks=max_picks)
