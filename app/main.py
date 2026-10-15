"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__
from app.routers import health

app = FastAPI(
    title="ThreatGraph",
    description="Cyber threat intelligence knowledge graph API.",
    version=__version__,
)
app.include_router(health.router)
