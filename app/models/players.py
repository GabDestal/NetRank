"""Schemas for player search, profile, match history and head-to-head."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Surface = Literal["Hard", "Clay", "Grass", "Carpet"]


class PlayerSummary(BaseModel):
    """Enough to identify a player in a list."""

    id: int
    name: str
    ioc: str | None = None
    hand: str | None = None
    dob: date | None = None


class PlayerHit(PlayerSummary):
    """A search result with its full-text relevance score."""

    score: float


class SurfaceRecord(BaseModel):
    """Wins and losses on one surface (walkovers excluded)."""

    surface: str
    wins: int
    losses: int
    winRate: float | None = Field(description="wins / (wins + losses); None without played matches.")


class PlayerProfile(PlayerSummary):
    """Biography plus career aggregates over the loaded scope (tour level, 1991 onward)."""

    height: int | None = None
    wikidataId: str | None = None
    matches: int
    wins: int
    losses: int
    titles: int = Field(description="Finals won.")
    bestRank: int | None = Field(description="Best ATP rank recorded at match time.")
    firstMatch: date | None
    lastMatch: date | None
    bySurface: list[SurfaceRecord]


class MatchOdds(BaseModel):
    """Closing odds from one bookmaker, seen from the player whose history is listed."""

    bookmaker: str
    playerOdds: float
    opponentOdds: float


class PlayerMatch(BaseModel):
    """One match in a player's history, from that player's point of view."""

    matchId: str
    date: date
    tournament: str
    tournamentId: str
    level: str
    surface: str | None
    round: str
    result: Literal["W", "L"]
    score: str
    walkover: bool
    retired: bool
    opponent: PlayerSummary
    odds: list[MatchOdds]


class HeadToHeadMatch(BaseModel):
    """One meeting between the two players."""

    matchId: str
    date: date
    tournament: str
    surface: str | None
    round: str
    winnerId: int
    score: str
    walkover: bool


class SurfaceHeadToHead(BaseModel):
    """Head-to-head on one surface (walkovers excluded)."""

    surface: str
    player1Wins: int
    player2Wins: int


class HeadToHead(BaseModel):
    """Head-to-head record between two players, overall and per surface (walkovers excluded)."""

    player1: PlayerSummary
    player2: PlayerSummary
    player1Wins: int
    player2Wins: int
    bySurface: list[SurfaceHeadToHead]
    matches: list[HeadToHeadMatch] = Field(description="Every meeting, most recent first (walkovers included).")
