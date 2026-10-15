"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError

from app import __version__
from app.database.connection import close_driver
from app.routers import cves, groups, health, products, techniques


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Close the Neo4j driver's connection pool when the API shuts down."""
    yield
    close_driver()


app = FastAPI(
    title="ThreatGraph",
    description="Cyber threat intelligence knowledge graph API: MITRE ATT&CK, CISA KEV, NVD and the CTID bridge.",
    version=__version__,
    lifespan=lifespan,
)


@app.exception_handler(DriverError)
@app.exception_handler(Neo4jError)
async def neo4j_unavailable(_request: Request, _exc: Exception) -> JSONResponse:
    """Answer 503 whenever Neo4j is unreachable or rejects a query, without leaking driver details."""
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "Neo4j is unavailable"})


for router_module in (health, groups, techniques, cves, products):
    app.include_router(router_module.router)
