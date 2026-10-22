"""Health endpoints used by Docker healthchecks, nginx and the container tests."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.database.client import Neo4jClient, get_db
from app.models.health import HealthResponse, ReadinessResponse
from app.services import health

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Liveness probe. Does not touch Neo4j, so a database outage does not restart the API."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "Neo4j is unreachable, rejects the credentials, or GDS is missing."}},
)
def readiness(response: Response, db: Annotated[Neo4jClient, Depends(get_db)]) -> ReadinessResponse:
    """Readiness probe: Neo4j answers and GDS is installed."""
    try:
        result = health.check_database(db)
    except (ServiceUnavailable, SessionExpired, AuthError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j unavailable ({type(exc).__name__})",
        ) from exc
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
