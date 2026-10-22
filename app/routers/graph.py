"""Endpoints relating two players: head-to-head and beat chains."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.database.client import Neo4jClient, get_db
from app.models.common import error_responses
from app.models.graph import BeatChain
from app.models.players import HeadToHead
from app.services import graph

router = APIRouter(prefix="/api", tags=["graph"])

Db = Annotated[Neo4jClient, Depends(get_db)]


@router.get("/h2h", response_model=HeadToHead, responses=error_responses(400, 404, 503))
def get_head_to_head(
    db: Db,
    p1: Annotated[int, Query(description="First player id.")],
    p2: Annotated[int, Query(description="Second player id.")],
) -> HeadToHead:
    """Every meeting between two players, with overall and per-surface records."""
    return graph.head_to_head(db, p1, p2)


@router.get("/path", response_model=BeatChain, responses=error_responses(400, 404, 503))
def get_beat_chain(
    db: Db,
    source: Annotated[int, Query(alias="from", description="Player at the start of the chain.")],
    target: Annotated[int, Query(alias="to", description="Player at the end of the chain.")],
    max_hops: Annotated[int, Query(ge=1, le=graph.MAX_HOPS, description="Longest chain accepted.")] = 4,
) -> BeatChain:
    """Shortest chain where each player beat the next (from > ... > to), each hop backed by a match."""
    return graph.beat_chain(db, source, target, max_hops)
