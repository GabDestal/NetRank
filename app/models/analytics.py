"""Schemas for GDS-backed endpoints: prestige, style similarity, styles and the admin refresh."""

from pydantic import BaseModel, Field

from app.models.common import Page
from app.models.players import PlayerSummary


class Era(BaseModel):
    """An inclusive range of seasons; None on all-time results."""

    label: str
    startYear: int
    endYear: int


class PlayerPrestige(BaseModel):
    """PageRank prestige of one player, all-time or within an era."""

    player: PlayerSummary
    era: Era | None = Field(description="None for all-time prestige.")
    score: float = Field(description="Weighted PageRank on who-beat-whom (losers point to winners).")
    rank: int = Field(description="1 = most prestigious among players ranked.")
    playersRanked: int
    percentile: float = Field(description="Share of ranked players below this one, in [0, 1].")


class PrestigeEntry(BaseModel):
    """One row of a prestige leaderboard."""

    rank: int
    player: PlayerSummary
    score: float


class PrestigeBoard(BaseModel):
    """Leaderboard for an era (or all-time)."""

    era: Era | None
    ranking: Page[PrestigeEntry]


class StyleFeatures(BaseModel):
    """Career serve/return percentages and surface win shares (fractions in [0, 1])."""

    acePct: float
    doubleFaultPct: float
    firstServeInPct: float
    firstServeWonPct: float
    secondServeWonPct: float
    breakPointsSavedPct: float
    returnPointsWonPct: float
    breakPointsConvertedPct: float
    clayWinShare: float
    grassWinShare: float
    hardWinShare: float


class SimilarPlayer(BaseModel):
    """A stylistic neighbour found by KNN on standardised style features."""

    player: PlayerSummary
    score: float = Field(description="KNN cosine similarity, higher is closer.")
    styleId: int | None
    features: StyleFeatures


class SimilarResult(BaseModel):
    """A player's style and their nearest stylistic neighbours."""

    player: PlayerSummary
    styleId: int | None
    features: StyleFeatures
    similar: Page[SimilarPlayer]


class StyleTrait(BaseModel):
    """A feature on which a style's centroid stands out, with a readable label."""

    feature: str
    zScore: float = Field(description="Centroid value in standard deviations from the mean of all styled players.")
    label: str


class StyleMember(BaseModel):
    """A player in a style community."""

    player: PlayerSummary
    prestigeRank: int | None
    matches: int = Field(description="Matches with serve statistics behind the style vector.")


class StyleSummary(BaseModel):
    """One style community found by Louvain on the KNN similarity graph."""

    id: int
    size: int
    traits: list[StyleTrait]
    examples: list[PlayerSummary] = Field(description="Most prestigious members.")


class StyleDetail(StyleSummary):
    """A style with its centroid and paginated members (most prestigious first)."""

    centroid: dict[str, float]
    members: Page[StyleMember]


class RefreshReport(BaseModel):
    """What POST /api/admin/gds/refresh computed."""

    prestige: dict
    styles: dict
    concurrency: int
    minMatches: int
    seconds: float
