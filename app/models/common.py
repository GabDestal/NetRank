"""Schemas shared by several endpoints: pagination and errors."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

Item = TypeVar("Item")

MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[Item]):
    """One page of a list endpoint. `total` counts every item, not just this page."""

    items: list[Item]
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total: int = Field(ge=0)


class ErrorResponse(BaseModel):
    """Body of every 4xx/5xx answer."""

    detail: str


def error_responses(*codes: int) -> dict[int, dict]:
    """OpenAPI `responses` entry documenting the given error codes with ErrorResponse."""
    descriptions = {
        400: "Invalid combination of parameters.",
        404: "Unknown player, or nothing found within the requested bounds.",
        503: "Neo4j is unavailable.",
    }
    return {code: {"model": ErrorResponse, "description": descriptions[code]} for code in codes}
