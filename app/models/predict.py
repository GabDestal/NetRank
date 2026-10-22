"""Schemas for GET /api/predict. Every probability carries a provenance tag (decision log D57)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.players import PlayerSummary


class Contribution(BaseModel):
    """One term of the model's linear score (positive favours player 1)."""

    feature: str
    logitContribution: float


class ModelPrediction(BaseModel):
    """What the graph model predicts."""

    tag: Literal["predicted"] = "predicted"
    p1WinProbability: float
    p2WinProbability: float
    modelVersion: str
    topContributions: list[Contribution]


class MarketProbability(BaseModel):
    """A bookmaker's closing odds for this match, margin removed."""

    tag: Literal["verified"] = "verified"
    bookmaker: str
    p1WinProbability: float
    p1Odds: float
    p2Odds: float


class MatchResult(BaseModel):
    """The recorded outcome of the match (only with match_id)."""

    tag: Literal["verified"] = "verified"
    matchId: str
    date: date
    winnerId: int
    score: str
    walkover: bool
    retired: bool


class Prediction(BaseModel):
    """Model probability, plus bookmaker probabilities and the result when a past match is given."""

    player1: PlayerSummary
    player2: PlayerSummary
    surface: str
    featuresBefore: date = Field(description="Every feature uses only matches dated before this day.")
    prediction: ModelPrediction
    market: list[MarketProbability] = Field(description="Empty unless match_id names a match with odds.")
    result: MatchResult | None = None
    notes: list[str] = Field(description="Caveats, e.g. a player without graph history before the cutoff.")
