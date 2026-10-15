"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.database.connection import close_driver
from app.routers import health


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Close the Neo4j driver's connection pool when the API shuts down."""
    yield
    close_driver()


app = FastAPI(
    title="ThreatGraph",
    description="Cyber threat intelligence knowledge graph API.",
    version=__version__,
    lifespan=lifespan,
)
app.include_router(health.router)
