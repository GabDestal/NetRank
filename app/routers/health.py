"""Liveness and database health endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from app.database.connection import get_driver
from app.models.health import DatabaseHealthResponse, HealthResponse
from app.services.health import neo4j_components

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the API process is up."""
    return HealthResponse(status="ok")


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Neo4j is unreachable or rejected the login"}},
)
def database_health(driver: Annotated[Driver, Depends(get_driver)]) -> DatabaseHealthResponse:
    """Report whether Neo4j answers, with its version and edition."""
    try:
        components = neo4j_components(driver)
    except (DriverError, Neo4jError) as exc:
        # The driver's message can contain connection details, so it is not returned to the client.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j is unavailable") from exc
    return DatabaseHealthResponse(status="ok", neo4j_version=components["version"],
                                  neo4j_edition=components["edition"])
