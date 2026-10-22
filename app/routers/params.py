"""Query parameters shared by list endpoints."""

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from app.errors import InvalidRequestError
from app.models.common import MAX_PAGE_SIZE
from app.models.players import Surface


@dataclass(frozen=True)
class Pagination:
    """1-based page number and page size."""

    page: int
    size: int


def pagination(
    page: Annotated[int, Query(ge=1, description="1-based page number.")] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Items per page.")] = 20,
) -> Pagination:
    """FastAPI dependency reading ?page=&size=."""
    return Pagination(page=page, size=size)


PageParams = Annotated[Pagination, Depends(pagination)]


def match_filters(
    surface: Surface | None = None,
    since: Annotated[date | None, Query(description="First match date included (YYYY-MM-DD).")] = None,
    until: Annotated[date | None, Query(description="Last match date included (YYYY-MM-DD).")] = None,
) -> dict:
    """FastAPI dependency reading ?surface=&since=&until=; rejects an inverted date range."""
    if since and until and since > until:
        raise InvalidRequestError("since must be on or before until")
    return {"surface": surface, "since": since, "until": until}


MatchFilters = Annotated[dict, Depends(match_filters)]
