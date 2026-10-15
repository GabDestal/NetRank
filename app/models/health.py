"""Schemas for the health endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Body returned by GET /health."""

    status: Literal["ok"]


class DatabaseHealthResponse(BaseModel):
    """Body returned by GET /health/db when Neo4j is reachable."""

    status: Literal["ok"]
    neo4j_version: str
    neo4j_edition: str
