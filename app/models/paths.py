"""Schemas for the group-to-product connection path (D20)."""

from typing import Literal

from pydantic import BaseModel, Field

PATH_NOTE = (
    "The group and the product are linked through a shared technique (CTID mapping). "
    "This is an association, not evidence that the group exploited this product."
)


class PathNode(BaseModel):
    """One node on the path, in order from the group to the product."""

    kind: Literal["Group", "Software", "Technique", "CVE", "Product"]
    id: str
    name: str | None = None


class PathHop(BaseModel):
    """The relationship between two consecutive nodes of the path."""

    type: str
    direction: Literal["forward", "backward"] = Field(
        description="forward if the relationship points from the earlier node to the later one")


class ConnectionResponse(BaseModel):
    """Body of GET /paths/connection."""

    group: PathNode
    product: PathNode
    max_hops: int
    hops: int
    nodes: list[PathNode]
    relationships: list[PathHop]
    reading: str
    note: str = PATH_NOTE
