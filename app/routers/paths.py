"""Path endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import GROUP_ID_PATTERN, ErrorResponse
from app.models.paths import ConnectionResponse
from app.services.paths import SEARCH_HOPS, PathNotFound, connection_path

router = APIRouter(prefix="/paths", tags=["paths"])


@router.get(
    "/connection",
    response_model=ConnectionResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse,
                                           "description": "Unknown group or product, or no path within max_hops"}},
)
def get_connection(
    driver: Annotated[Driver, Depends(get_driver)],
    group: Annotated[str, Query(pattern=GROUP_ID_PATTERN, description="ATT&CK group id, e.g. G0016")],
    product: Annotated[str, Query(min_length=3, max_length=300,
                                  description="Product key as vendor:product, e.g. fortinet:fortios")],
    max_hops: Annotated[int, Query(ge=1, le=SEARCH_HOPS, description="Longest path accepted")] = 6,
) -> ConnectionResponse:
    """How is this group connected to this product? The shortest path over verified links only:
    the group (or its software) uses a technique that a CVE affecting the product is mapped to."""
    try:
        return connection_path(driver, group, product, max_hops=max_hops)
    except PathNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
