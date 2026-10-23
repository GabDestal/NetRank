"""GDS tests on live Neo4j: era PageRank, FastRP determinism and cutoff, refresh determinism.

The synthetic matches are dated in 1900, before any real data (1991+), so era and FastRP windows
see only them even on a fully loaded database. Tests run with GDS_CONCURRENCY=1 (tests/conftest.py).
"""

from datetime import date

import pytest

from app.services import gds
from scripts import ingest

pytestmark = pytest.mark.integration

A, B, C, D, E, F, LATE = -21, -22, -23, -24, -25, -26, -27
PLAYERS = [A, B, C, D, E, F, LATE]
# A beats everyone; then a descending ladder B > C > D > E > F.
RESULTS = [(A, B), (A, C), (A, D), (A, E), (A, F), (B, C), (C, D), (D, E), (E, F), (B, D), (C, E)]
STATS = {
    "aces": 5,
    "doubleFaults": 2,
    "servePoints": 60,
    "firstServesIn": 36,
    "firstServeWon": 27,
    "secondServeWon": 12,
    "serviceGames": 10,
    "breakPointsSaved": 3,
    "breakPointsFaced": 5,
}
CUTOFF = date(1900, 2, 1)

CLEANUP = """
MATCH (n)
WHERE (n:Player AND n.id IN [-21, -22, -23, -24, -25, -26, -27])
   OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TESTGDS-')
DETACH DELETE n
"""


def match(number, winner, loser, day):
    """Match record dated 1900 with identical serve statistics on both sides."""
    return {
        "id": f"TESTGDS-T-{number}",
        "tournamentId": "TESTGDS-T",
        "date": day,
        "round": "R32",
        "bestOf": 3,
        "score": "6-4 6-4",
        "minutes": 90,
        "surface": "Clay" if number % 2 else "Hard",
        "walkover": False,
        "retired": False,
        "winnerId": winner,
        "loserId": loser,
        "winner": {**STATS, "aces": 5 + (winner % 3)},
        "loser": {**STATS, "aces": 4 + (loser % 2)},
    }


def load_matches(db, rows):
    """Merge match rows through the production ingestion query."""
    ingest.load(db, ingest.MERGE_MATCHES, rows, "matches")


@pytest.fixture(name="gds_graph", scope="module")
def fixture_gds_graph(neo4j_client):
    """Synthetic players and January-1900 matches; everything removed and GDS results rebuilt afterwards."""
    db = neo4j_client
    db.write(CLEANUP)
    ingest.ensure_schema(db)
    ingest.load(db, ingest.MERGE_PLAYERS, [{"id": p, "name": f"Gdstest {abs(p)}"} for p in PLAYERS], "players")
    ingest.load(db, ingest.MERGE_TOURNAMENTS, [{"id": "TESTGDS-T", "name": "GDS Open", "year": 1900}], "tournaments")
    load_matches(db, [match(i, w, l, date(1900, 1, 1 + i)) for i, (w, l) in enumerate(RESULTS)])
    ingest.derive_beat(db)
    gds.clear_era_cache()
    yield db
    db.write(CLEANUP)
    ingest.derive_beat(db)
    gds.clear_era_cache()
    gds.refresh(db)


def test_era_pagerank_ranks_the_dominant_player_first(gds_graph):
    """In the 1900 window only the synthetic players exist; A, who beat everyone, ranks first."""
    ranking = gds.era_ranking(gds_graph, 1900, 1900)
    assert {row["id"] for row in ranking} == {A, B, C, D, E, F}
    assert [row["id"] for row in ranking][:2] == [A, B]
    assert not gds_graph.read(
        "CALL gds.graph.list() YIELD graphName WHERE graphName STARTS WITH 'netrank-era' " + "RETURN graphName"
    )


def test_fastrp_is_deterministic(gds_graph):
    """Same cutoff and seed: identical embeddings of the requested dimension."""
    first = gds.fastrp_embeddings(gds_graph, CUTOFF, dimension=16)
    second = gds.fastrp_embeddings(gds_graph, CUTOFF, dimension=16)
    assert first == second
    assert set(first) == {A, B, C, D, E, F} and len(first[A]) == 16


def test_fastrp_ignores_matches_after_the_cutoff(gds_graph):
    """A match after the cutoff changes nothing before it, and its new player only appears later."""
    before = gds.fastrp_embeddings(gds_graph, CUTOFF, dimension=16)
    load_matches(gds_graph, [match(99, LATE, A, date(1900, 3, 1))])
    try:
        assert gds.fastrp_embeddings(gds_graph, CUTOFF, dimension=16) == before
        assert LATE in gds.fastrp_embeddings(gds_graph, date(1900, 4, 1), dimension=16)
    finally:
        gds_graph.write("MATCH (m:Match {id: 'TESTGDS-T-99'}) DETACH DELETE m")


def test_refresh_is_reproducible(gds_graph):
    """Two refreshes give the same prestige ranks, style ids and SIMILAR_STYLE edges (concurrency 1, seed)."""
    snapshot = """
    MATCH (p:Player) WHERE p.id IN [-21, -22, -23, -24, -25, -26]
    OPTIONAL MATCH (p)-[s:SIMILAR_STYLE]->(o:Player)
    WITH p, o, s ORDER BY o.id
    RETURN p.id AS id, p.prestigeRank AS rank, p.styleId AS style,
           collect([o.id, round(s.score, 6)]) AS similar
    ORDER BY id
    """
    runs = []
    for _ in range(2):
        gds.refresh_prestige(gds_graph)
        report = gds.refresh_styles(gds_graph, min_matches=1)
        runs.append(gds_graph.read(snapshot))
    assert runs[0] == runs[1]
    assert report["players"] >= 6 and all(row["style"] is not None for row in runs[0])
    assert all(row["rank"] is not None for row in runs[0])
    assert not gds_graph.read("CALL gds.graph.list() YIELD graphName RETURN graphName")
