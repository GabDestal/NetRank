"""FastAPI entry point: `uvicorn app.main:app`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.database.client import Neo4jClient
from app.routers import health


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
