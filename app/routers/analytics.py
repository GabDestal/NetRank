"""GDS-backed endpoints: prestige, similar players, styles, and the admin refresh."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.config import get_settings
from app.database.client import Neo4jClient, get_db
from app.models.analytics import PlayerPrestige, PrestigeBoard, RefreshReport, SimilarResult, StyleDetail, StyleSummary
from app.models.common import Page, error_responses
from app.routers.params import PageParams
from app.security import ADMIN_ONLY
from app.services import analytics, gds

router = APIRouter(prefix="/api", tags=["analytics"])
admin = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[ADMIN_ONLY])

Db = Annotated[Neo4jClient, Depends(get_db)]
PlayerId = Annotated[int, Path(description="Sackmann player id, e.g. 103819 for Roger Federer.")]
EraParam = Annotated[
    str | None,
    Query(description="'2000s', '2004-2008' or '2010'; omit for all-time.", max_length=12),
]


@router.get("/players/{player_id}/prestige", response_model=PlayerPrestige, responses=error_responses(400, 404, 503))
def get_prestige(db: Db, player_id: PlayerId, era: EraParam = None) -> PlayerPrestige:
    """PageRank prestige: all-time (stored by the refresh) or within an era (computed per era, cached)."""
    return analytics.player_prestige(db, player_id, analytics.parse_era(era))


@router.get("/prestige", response_model=PrestigeBoard, responses=error_responses(400, 404, 503))
def get_prestige_board(db: Db, paging: PageParams, era: EraParam = None) -> PrestigeBoard:
    """Prestige leaderboard, all-time or within an era."""
    return analytics.prestige_board(db, analytics.parse_era(era), paging.page, paging.size)


@router.get("/players/{player_id}/similar", response_model=SimilarResult, responses=error_responses(404, 503))
def get_similar(db: Db, player_id: PlayerId, paging: PageParams) -> SimilarResult:
    """Players with the closest playing style (KNN on standardised serve/return/surface features)."""
    return analytics.similar(db, player_id, paging.page, paging.size, get_settings().style_min_matches)


@router.get("/styles", response_model=Page[StyleSummary], responses=error_responses(503))
def get_styles(db: Db, paging: PageParams) -> Page[StyleSummary]:
    """Playing-style communities (Louvain on the style-similarity graph), largest first."""
    return analytics.styles(db, paging.page, paging.size)


@router.get("/styles/{style_id}", response_model=StyleDetail, responses=error_responses(404, 503))
def get_style(
    db: Db, style_id: Annotated[int, Path(ge=1, description="Style id from GET /api/styles.")], paging: PageParams
) -> StyleDetail:
    """One style: readable traits, centroid in standard deviations, members by prestige."""
    return analytics.style(db, style_id, paging.page, paging.size)


@admin.post(
    "/gds/refresh",
    response_model=RefreshReport,
    responses={
        401: {"description": "Missing X-API-Key."},
        403: {"description": "Wrong X-API-Key."},
        **error_responses(503),
    },
)
def refresh_gds(db: Db) -> RefreshReport:
    """Recompute all-time prestige, style vectors, SIMILAR_STYLE and styles; clears the era cache."""
    return RefreshReport(**gds.refresh(db))
