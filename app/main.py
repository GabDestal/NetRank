"""FastAPI entry point: `uvicorn app.main:app`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app import __version__
from app.config import get_settings
from app.database.client import Neo4jClient
from app.errors import InvalidRequestError, NotFoundError
from app.routers import graph, health, players

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(api: FastAPI) -> AsyncIterator[None]:
    """Open the Neo4j driver at startup and close it at shutdown."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    api.state.db = Neo4jClient.from_settings(settings)
    try:
        yield
    finally:
        api.state.db.close()


app = FastAPI(
    title="NetRank API",
    version=__version__,
    description="Tennis knowledge graph: prestige, playing styles, beat chains and match predictions.",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(players.router)
app.include_router(graph.router)


@app.exception_handler(NotFoundError)
async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    """404 with the service's message."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidRequestError)
async def invalid_request(_: Request, exc: InvalidRequestError) -> JSONResponse:
    """400 with the service's message."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ServiceUnavailable)
@app.exception_handler(SessionExpired)
@app.exception_handler(AuthError)
async def database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    """503 when Neo4j cannot be reached; the driver's message is logged, not returned."""
    log.error(f"Neo4j unavailable: {exc!r}")
    return JSONResponse(status_code=503, content={"detail": f"Neo4j unavailable ({type(exc).__name__})"})
