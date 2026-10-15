"""Liveness and database health endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import ErrorResponse
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
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                     "description": "Neo4j is unreachable or rejected the login"}},
)
def database_health(driver: Annotated[Driver, Depends(get_driver)]) -> DatabaseHealthResponse:
    """Report whether Neo4j answers, with its version and edition. Neo4j errors become a 503 (see app.main)."""
    components = neo4j_components(driver)
    return DatabaseHealthResponse(status="ok", neo4j_version=components["version"],
                                  neo4j_edition=components["edition"])
