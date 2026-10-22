"""Leakage tests for the match-outcome features, on a synthetic graph dated 1901-1903.

Real data starts in 1991, so every snapshot and history window here sees only the synthetic matches.
The target match M is played on 1902-03-03 between P1 and P2.
"""

from datetime import date

import pytest

from app.ml import features as F
from scripts import ingest, train

pytestmark = pytest.mark.integration

P1, P2, X, Y, Z = -31, -32, -33, -34, -35
M_DATE = date(1902, 3, 3)
BASE = [  # (match number, date, winner, loser)
    (1, date(1901, 2, 4), P1, X),
    (2, date(1901, 3, 4), X, P2),
    (3, date(1901, 5, 6), P2, Y),
    (4, date(1901, 9, 2), P1, P2),
    (5, date(1902, 1, 6), P2, Z),   # same season as M, before it: history yes, snapshot no
    (6, M_DATE, P1, P2),            # the target match M
    (7, M_DATE, X, Y),              # same day as M
]
CLEANUP = """
MATCH (n)
WHERE (n:Player AND n.id IN [-31, -32, -33, -34, -35]) OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TESTML-')
DETACH DELETE n
"""


def row(number, day, winner, loser, surface="Hard"):
    """Match record for the ingestion query."""
    return {
        "id": f"TESTML-T-{number}", "tournamentId": "TESTML-T", "date": day, "round": "R32", "bestOf": 3,
        "score": "6-4 6-4", "minutes": 80, "surface": surface, "walkover": False, "retired": False,
        "winnerId": winner, "loserId": loser, "winner": {"rank": 10}, "loser": {"rank": 20},
    }


def load(db, results):
    """Merge (number, date, winner, loser) tuples as matches."""
    ingest.load(db, ingest.MERGE_MATCHES, [row(*r) for r in results], "matches")


def serving_features(db) -> dict:
    """Features of M through the prediction-time path (snapshot at Jan 1 1902, history before M)."""
    snapshot = F.build_snapshot(db, F.season_cutoff(M_DATE))
    history = F.history_before(db, P1, P2, M_DATE)
    return F.feature_vector(snapshot, history, (P1, P2), "Hard")


@pytest.fixture(name="ml_graph")
def fixture_ml_graph(neo4j_client):
    """Fresh synthetic graph for each test (tests add matches)."""
    db = neo4j_client
    db.write(CLEANUP)
    ingest.ensure_schema(db)
    ingest.load(db, ingest.MERGE_PLAYERS, [{"id": p, "name": f"Mltest {abs(p)}"} for p in (P1, P2, X, Y, Z)], "players")
    ingest.load(db, ingest.MERGE_TOURNAMENTS, [{"id": "TESTML-T", "name": "ML Open", "year": 1901}], "tournaments")
    load(db, BASE)
    yield db
    db.write(CLEANUP)


def test_no_feature_uses_the_match_date_or_later(ml_graph):
    """Results on M's date and afterwards (including a P2 winning streak) leave M's features unchanged."""
    before = serving_features(ml_graph)
    load(ml_graph, [
        (20, M_DATE, P2, P1),               # a same-day rematch
        (21, M_DATE, P2, X),
        (22, date(1902, 6, 2), P2, P1),
        (23, date(1903, 1, 5), P2, Y),
        (24, date(1903, 2, 2), Z, P1),      # a later loss for P1 must not reach M either
    ])
    assert serving_features(ml_graph) == before


def test_the_check_can_fail(ml_graph):
    """Control: a match BEFORE M's date does change M's history features (the test is not vacuous)."""
    before = serving_features(ml_graph)
    load(ml_graph, [(30, date(1902, 2, 3), P2, P1)])
    after = serving_features(ml_graph)
    assert after["headToHead"] != before["headToHead"]
    assert after["logPrestige"] == before["logPrestige"]  # same season: snapshot (Jan 1) unchanged


def test_history_respects_the_season_snapshot_and_the_day(ml_graph):
    """Head-to-head counts match 4 (P1 beat P2 in 1901) but not M itself; experience counts match 5."""
    values = serving_features(ml_graph)
    assert values["headToHead"] == 1.0  # 1-0 before M
    history = F.history_before(ml_graph, P1, P2, M_DATE)
    assert (history.played[P1], history.played[P2]) == (2, 4)


def test_training_and_serving_paths_agree(ml_graph):
    """The batch builder used by make train produces the same features as /api/predict for M."""
    matches = [
        {"id": f"TESTML-T-{n}", "date": d, "surface": "Hard", "walkover": False, "retired": False,
         "winnerId": w, "loserId": l, "winnerRank": 10, "loserRank": 20, "pinnacle": None, "bet365": None}
        for n, d, w, l in BASE
    ]
    dataset = train.build_dataset(ml_graph, matches, first_season=1901)
    m_row = dataset[dataset["matchId"] == "TESTML-T-6"].iloc[0]
    p1_won = train.p1_is_winner("TESTML-T-6")
    players = (P1, P2) if p1_won else (P2, P1)
    snapshot = F.build_snapshot(ml_graph, F.season_cutoff(M_DATE))
    expected = F.feature_vector(snapshot, F.history_before(ml_graph, *players, M_DATE), players, "Hard")
    assert {name: m_row[name] for name in F.FEATURES} == pytest.approx(expected)
    assert m_row["label"] == int(p1_won)
