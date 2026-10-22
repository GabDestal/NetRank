"""Player endpoints: search, profile, match history and nemeses."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.database.client import Neo4jClient, get_db
from app.models.common import Page, error_responses
from app.models.graph import NemesisReport
from app.models.players import PlayerHit, PlayerMatch, PlayerProfile
from app.routers.params import MatchFilters, PageParams
from app.services import graph, players

router = APIRouter(prefix="/api/players", tags=["players"])

Db = Annotated[Neo4jClient, Depends(get_db)]
PlayerId = Annotated[int, Path(description="Sackmann player id, e.g. 103819 for Roger Federer.")]


@router.get("", response_model=Page[PlayerHit], responses=error_responses(503))
def search_players(
    db: Db,
    paging: PageParams,
    q: Annotated[str, Query(min_length=2, max_length=60, description="Name or part of it, e.g. 'fed' or 'nunez'.")],
) -> Page[PlayerHit]:
    """Search players by name: every word is a prefix, accents and case are ignored."""
    return players.search(db, q, paging.page, paging.size)


@router.get("/{player_id}", response_model=PlayerProfile, responses=error_responses(404, 503))
def get_player(db: Db, player_id: PlayerId) -> PlayerProfile:
    """Biography and career record (tour level, 1991 onward): wins, titles, best rank, per surface."""
    return players.profile(db, player_id)


@router.get("/{player_id}/matches", response_model=Page[PlayerMatch], responses=error_responses(400, 404, 503))
def get_player_matches(db: Db, player_id: PlayerId, paging: PageParams, filters: MatchFilters) -> Page[PlayerMatch]:
    """A player's matches, most recent first, with opponent, score and closing odds.

    Filters: surface, since and until (inclusive dates).
    """
    return players.matches(db, player_id, filters, paging.page, paging.size)


@router.get("/{player_id}/nemesis", response_model=NemesisReport, responses=error_responses(404, 503))
def get_nemesis(
    db: Db,
    player_id: PlayerId,
    paging: PageParams,
    min_wins: Annotated[int, Query(ge=1, le=50, description="Opponents need at least this many wins.")] = 2,
    triangles: Annotated[int, Query(ge=0, le=50, description="How many triangles to return.")] = 10,
) -> NemesisReport:
    """Who beats this player most, and non-transitive triangles (player > B > C > player)."""
    return graph.nemesis(db, player_id, {"minWins": min_wins, "triangles": triangles}, paging.page, paging.size)
