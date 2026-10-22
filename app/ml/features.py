"""Leakage-free features for "does p1 beat p2?", shared by training (scripts/train.py) and /api/predict.

Two sources, both strictly before the match (decision log D50):
- a Snapshot at a cutoff date: cumulative PageRank, recent PageRank (2 seasons) and FastRP embeddings,
  each computed only from played matches dated before the cutoff. Training uses the cutoff
  Jan 1 of the match's season.
- History counters replayed match by match: experience, surface record and head-to-head. All matches
  sharing a date are scored before any of them is recorded, so a match never sees itself or a
  same-day result (Sackmann dates every match of an event with the event's start date).

Every feature is a difference p1 - p2 (or an antisymmetric pair statistic), so swapping the players
negates the vector (decision log D51).
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.database.client import Neo4jClient
from app.services import gds

RECENT_SEASONS = 2
BASE_PAGERANK = 0.15  # 1 - damping: the score of a player nobody lost to; used for unseen players
SURFACES = ("Hard", "Clay", "Grass", "Carpet")
SCALAR_FEATURES = (
    "logPrestige",
    "logRecentPrestige",
    "unseen",
    "inactiveRecently",
    "logExperience",
    "surfaceWinRate",
    "headToHead",
    "headToHeadShare",
)
EMBEDDING_FEATURES = tuple(f"fastrp{i:02d}" for i in range(gds.FASTRP_DIMENSION))
FEATURES = SCALAR_FEATURES + EMBEDDING_FEATURES

# Both players' played matches before a date, for replaying history at prediction time.
HISTORY = """
MATCH (p:Player)-[:WON|LOST]->(m:Match)
WHERE p.id IN [$p1, $p2] AND m.date < $before AND NOT m.walkover
WITH DISTINCT m
MATCH (w:Player)-[:WON]->(m)<-[:LOST]-(l:Player)
RETURN m.date AS date, w.id AS winnerId, l.id AS loserId, m.surface AS surface
ORDER BY date, m.id
"""


@dataclass(frozen=True)
class Snapshot:
    """Graph features of every player computed only from matches dated before `cutoff`."""

    cutoff: date
    prestige: dict[int, float]
    recent: dict[int, float]
    embeddings: dict[int, list[float]]


def build_snapshot(db: Neo4jClient, cutoff: date) -> Snapshot:
    """Cumulative and recent PageRank plus FastRP, all from played matches before `cutoff`."""
    recent_start = date(cutoff.year - RECENT_SEASONS, cutoff.month, cutoff.day)
    return Snapshot(
        cutoff=cutoff,
        prestige={row["id"]: row["score"] for row in gds.pagerank_window(db, None, cutoff)},
        recent={row["id"]: row["score"] for row in gds.pagerank_window(db, recent_start, cutoff)},
        embeddings=gds.fastrp_embeddings(db, cutoff),
    )


@dataclass
class History:
    """Running counters over played matches: experience, surface record, head-to-head."""

    played: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    surface_played: dict[tuple[int, str], int] = field(default_factory=lambda: defaultdict(int))
    surface_won: dict[tuple[int, str], int] = field(default_factory=lambda: defaultdict(int))
    pair_wins: dict[tuple[int, int], int] = field(default_factory=lambda: defaultdict(int))

    def record(self, winner: int, loser: int, surface: str | None) -> None:
        """Add one played match."""
        self.played[winner] += 1
        self.played[loser] += 1
        self.pair_wins[(winner, loser)] += 1
        if surface:
            self.surface_played[(winner, surface)] += 1
            self.surface_played[(loser, surface)] += 1
            self.surface_won[(winner, surface)] += 1

    def surface_rate(self, player: int, surface: str | None) -> float:
        """Win rate on `surface`, smoothed towards 0.5: (wins + 1) / (played + 2)."""
        if not surface:
            return 0.5
        return (self.surface_won[(player, surface)] + 1) / (self.surface_played[(player, surface)] + 2)

    def features(self, p1: int, p2: int, surface: str | None) -> dict[str, float]:
        """History features of p1 relative to p2 at the current point of the replay."""
        wins, losses = self.pair_wins[(p1, p2)], self.pair_wins[(p2, p1)]
        return {
            "logExperience": math.log1p(self.played[p1]) - math.log1p(self.played[p2]),
            "surfaceWinRate": self.surface_rate(p1, surface) - self.surface_rate(p2, surface),
            "headToHead": float(wins - losses),
            "headToHeadShare": (wins + 1) / (wins + losses + 2) - 0.5,
        }


def replay(matches: Iterable[dict]) -> History:
    """History after recording the given played matches (dicts with winnerId, loserId, surface)."""
    history = History()
    for match in matches:
        history.record(match["winnerId"], match["loserId"], match["surface"])
    return history


def history_before(db: Neo4jClient, p1: int, p2: int, before: date) -> History:
    """Replay both players' played matches dated strictly before `before` (prediction-time path)."""
    return replay(db.read(HISTORY, {"p1": p1, "p2": p2, "before": before}))


def snapshot_features(snapshot: Snapshot, p1: int, p2: int) -> dict[str, float]:
    """Graph features of p1 relative to p2 from a snapshot; unseen players are flagged, not zero-filled."""
    seen1, seen2 = p1 in snapshot.embeddings, p2 in snapshot.embeddings
    zeros = [0.0] * gds.FASTRP_DIMENSION
    emb1, emb2 = snapshot.embeddings.get(p1, zeros), snapshot.embeddings.get(p2, zeros)
    values = {
        "logPrestige": math.log(snapshot.prestige.get(p1, BASE_PAGERANK))
        - math.log(snapshot.prestige.get(p2, BASE_PAGERANK)),
        "logRecentPrestige": math.log(snapshot.recent.get(p1, BASE_PAGERANK))
        - math.log(snapshot.recent.get(p2, BASE_PAGERANK)),
        "unseen": float(not seen1) - float(not seen2),
        "inactiveRecently": float(p1 not in snapshot.recent) - float(p2 not in snapshot.recent),
    }
    values.update({name: a - b for name, a, b in zip(EMBEDDING_FEATURES, emb1, emb2)})
    return values


def feature_vector(snapshot: Snapshot, history: History, players: tuple[int, int], surface: str | None) -> dict:
    """All features, keyed by name in FEATURES order."""
    p1, p2 = players
    values = {**snapshot_features(snapshot, p1, p2), **history.features(p1, p2, surface)}
    return {name: values[name] for name in FEATURES}


def season_cutoff(day: date) -> date:
    """Snapshot cutoff used for a match on `day`: Jan 1 of its season."""
    return date(day.year, 1, 1)


def devig(odds_p1: float, odds_p2: float) -> float:
    """Bookmaker probability that p1 wins with the margin removed: (1/o1) / (1/o1 + 1/o2)."""
    return (1 / odds_p1) / (1 / odds_p1 + 1 / odds_p2)
