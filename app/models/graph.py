"""Schemas for graph-pattern endpoints: nemesis, non-transitive triangles and beat chains."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.common import Page
from app.models.players import PlayerSummary


class Nemesis(BaseModel):
    """An opponent and how the head-to-head with them stands."""

    opponent: PlayerSummary
    winsOverPlayer: int = Field(description="Played matches the opponent won against the player.")
    lossesToPlayer: int
    lastWinOverPlayer: date


class Triangle(BaseModel):
    """player > second > third > player, each '>' a strict head-to-head lead (decision log D34)."""

    second: PlayerSummary
    third: PlayerSummary
    record: list[str] = Field(description="Head-to-head of each edge, e.g. ['3-1', '2-0', '4-2'].")
    weakestLead: int = Field(description="Smallest margin of the three leads; triangles are sorted by it.")


class NemesisReport(BaseModel):
    """Nemeses (paginated) and the strongest non-transitive triangles through the player."""

    player: PlayerSummary
    nemeses: Page[Nemesis]
    triangleCount: int
    triangles: list[Triangle]


class ChainHop(BaseModel):
    """One step of a beat chain, backed by the most recent played match where `winner` beat `loser`."""

    winner: PlayerSummary
    loser: PlayerSummary
    wins: int = Field(description="All played wins of `winner` over `loser`.")
    matchId: str
    date: date
    tournament: str
    round: str
    score: str


class BeatChain(BaseModel):
    """Shortest chain from `source` to `target` where each player beat the next one."""

    source: PlayerSummary
    target: PlayerSummary
    hops: int
    chain: list[ChainHop]
