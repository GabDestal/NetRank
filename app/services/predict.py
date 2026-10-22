"""GET /api/predict: model probability for p1 vs p2, leakage-free by construction.

Without match_id the features use the serving snapshot shipped with the model (all data before its
cutoff). With match_id they are rebuilt exactly as in training: snapshot at Jan 1 of the match's
season and history before the match date, so a past match is predicted without knowing its result;
its bookmaker odds (margin removed) and actual result are returned alongside, tagged "verified".
"""

import threading
from collections import OrderedDict
from datetime import date

from app.config import get_settings
from app.database.client import Neo4jClient
from app.errors import InvalidRequestError, NotFoundError
from app.ml import features as F
from app.ml.model import load_model
from app.models.predict import Prediction

SNAPSHOT_CACHE_SIZE = 4

PLAYERS = """
MATCH (p:Player)
WHERE p.id IN [$p1, $p2]
RETURN p {.id, .name, .ioc, .hand, .dob} AS player
"""

MATCH_INFO = """
MATCH (w:Player)-[:WON]->(m:Match {id: $matchId})<-[:LOST]-(l:Player)
RETURN m.id AS matchId, m.date AS date, m.surface AS surface, m.score AS score, m.walkover AS walkover,
       m.retired AS retired, w.id AS winnerId, l.id AS loserId,
       [(b:Bookmaker)-[pr:PRICED]->(m) | {bookmaker: b.name, winnerOdds: pr.winnerOdds, loserOdds: pr.loserOdds}]
         AS odds
"""

_snapshots: OrderedDict[date, F.Snapshot] = OrderedDict()
_snapshot_lock = threading.Lock()


def season_snapshot(db: Neo4jClient, cutoff: date) -> F.Snapshot:
    """Snapshot at `cutoff`, cached (a few seconds to build: two PageRanks and FastRP)."""
    with _snapshot_lock:
        if cutoff not in _snapshots:
            _snapshots[cutoff] = F.build_snapshot(db, cutoff)
            if len(_snapshots) > SNAPSHOT_CACHE_SIZE:
                _snapshots.popitem(last=False)
        _snapshots.move_to_end(cutoff)
        return _snapshots[cutoff]


def players(db: Neo4jClient, p1: int, p2: int) -> tuple[dict, dict]:
    """Both player summaries; 400 for the same player twice, 404 for an unknown id."""
    if p1 == p2:
        raise InvalidRequestError("p1 and p2 must be different players")
    found = {row["player"]["id"]: row["player"] for row in db.read(PLAYERS, {"p1": p1, "p2": p2})}
    missing = [str(pid) for pid in (p1, p2) if pid not in found]
    if missing:
        raise NotFoundError(f"No player with id {', '.join(missing)}")
    return found[p1], found[p2]


def past_match(db: Neo4jClient, match_id: str, p1: int, p2: int, surface: str | None) -> dict:
    """The match named by match_id; it must be between p1 and p2, and agree with surface if given."""
    rows = db.read(MATCH_INFO, {"matchId": match_id})
    if not rows:
        raise NotFoundError(f"No match with id {match_id}")
    match = rows[0]
    if {match["winnerId"], match["loserId"]} != {p1, p2}:
        raise InvalidRequestError(f"Match {match_id} is not between players {p1} and {p2}")
    if surface and match["surface"] and surface != match["surface"]:
        raise InvalidRequestError(f"Match {match_id} was played on {match['surface']}, not {surface}")
    return match


def market(match: dict, p1: int) -> list[dict]:
    """Bookmaker probabilities for p1, margin removed, from the match's closing odds."""
    entries = []
    for price in sorted(match["odds"], key=lambda o: o["bookmaker"]):
        p1_odds, p2_odds = (
            (price["winnerOdds"], price["loserOdds"]) if match["winnerId"] == p1
            else (price["loserOdds"], price["winnerOdds"])
        )
        entries.append({"bookmaker": price["bookmaker"], "p1WinProbability": round(F.devig(p1_odds, p2_odds), 4),
                        "p1Odds": p1_odds, "p2Odds": p2_odds})
    return entries


def notes_for(snapshot: F.Snapshot, ids: tuple[int, int], names: tuple[str, str]) -> list[str]:
    """Caveats about missing graph history."""
    notes = []
    for pid, name in zip(ids, names):
        if pid not in snapshot.embeddings:
            notes.append(f"{name} has no played match before {snapshot.cutoff}: graph features are flagged as unseen")
        elif pid not in snapshot.recent:
            notes.append(f"{name} played no match in the {F.RECENT_SEASONS} seasons before {snapshot.cutoff}")
    return notes


def predict(db: Neo4jClient, p1: int, p2: int, surface: str | None, match_id: str | None) -> Prediction:
    """Model probability that p1 beats p2, with market and result for a past match."""
    model = load_model(get_settings().model_path)
    player1, player2 = players(db, p1, p2)
    if match_id:
        match = past_match(db, match_id, p1, p2, surface)
        surface, before = match["surface"] or surface, match["date"]
        snapshot = season_snapshot(db, F.season_cutoff(before))
    else:
        if not surface:
            raise InvalidRequestError("surface is required unless match_id is given")
        match, snapshot = None, model.snapshot
        before = snapshot.cutoff
    values = F.feature_vector(snapshot, F.history_before(db, p1, p2, before), (p1, p2), surface)
    probability = model.probability(values)
    result = None
    if match:
        result = {key: match[key] for key in ("matchId", "date", "winnerId", "score", "walkover", "retired")}
    return Prediction(
        player1=player1,
        player2=player2,
        surface=surface or "Unknown",
        featuresBefore=before,
        prediction={
            "p1WinProbability": round(probability, 4),
            "p2WinProbability": round(1 - probability, 4),
            "modelVersion": model.version,
            "topContributions": model.contributions(values),
        },
        market=market(match, p1) if match else [],
        result=result,
        notes=notes_for(snapshot, (p1, p2), (player1["name"], player2["name"])),
    )
