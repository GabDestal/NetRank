"""Response schemas for the liveness and readiness probes."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: the API process is up and serving requests."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness: Neo4j answers and the GDS plugin is installed."""

    status: Literal["ok", "degraded"] = Field(description="'degraded' when Neo4j answers but GDS is missing.")
    neo4j_version: str
    neo4j_edition: str
    gds_version: str | None = Field(default=None, description="None when the GDS plugin is not loaded.")
