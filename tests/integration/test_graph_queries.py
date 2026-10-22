"""Cypher tests for the endpoint queries on a small synthetic graph with known answers.

Players (negative ids, so they never collide with real data):
  A (-11) leads B 2-1;  B (-12) beat C once;  C (-13) beat A once  -> triangle A > B > C > A
  C beat D (-14) once;  D beat C by walkover only (no BEAT edge, not counted)
"""

from datetime import date

import pytest

from app.errors import InvalidRequestError, NotFoundError
from app.services import graph, players
from scripts import ingest

pytestmark = pytest.mark.integration

A, B, C, D = -11, -12, -13, -14
NAMES = {A: "Testplayer Alpha", B: "Testplayer Bravo", C: "Testplayer Charlie", D: "Testplayer Delta"}
RESULTS = [  # (match number, winner, loser, surface, walkover)
    (1, A, B, "Clay", False),
    (2, A, B, "Grass", False),
    (3, B, A, "Clay", False),
    (4, B, C, "Hard", False),
    (5, C, A, "Hard", False),
    (6, C, D, "Hard", False),
    (7, D, C, "Hard", True),
]

CLEANUP = """
MATCH (n)
WHERE (n:Player AND n.id IN [-11, -12, -13, -14]) OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TESTG-')
DETACH DELETE n
"""


def match_row(number, winner, loser, surface, walkover):
    """A match record in the shape scripts.sackmann.match_records produces."""
    return {
        "id": f"TESTG-T-{number}",
        "tournamentId": "TESTG-T",
        "date": date(2000, 1, number),
        "round": "F" if number == 1 else "R32",
        "bestOf": 3,
        "score": "W/O" if walkover else "6-4 6-4",
        "minutes": None,
        "surface": surface,
        "walkover": walkover,
        "retired": False,
        "winnerId": winner,
        "loserId": loser,
        "winner": {"rank": 10},
        "loser": {"rank": 20},
    }


@pytest.fixture(name="mini_graph", scope="module")
def fixture_mini_graph(neo4j_client):
    """Load the synthetic graph and derive BEAT; remove it (and rebuild BEAT) afterwards."""
    db = neo4j_client
    db.write(CLEANUP)
    ingest.ensure_schema(db)
    ingest.load(db, ingest.MERGE_PLAYERS, [{"id": pid, "name": name} for pid, name in NAMES.items()], "players")
    tournament = [{"id": "TESTG-T", "name": "Test Open", "year": 2000, "level": "A", "levelName": "ATP Tour"}]
    ingest.load(db, ingest.MERGE_TOURNAMENTS, tournament, "tournaments")
    ingest.load(db, ingest.MERGE_MATCHES, [match_row(*r) for r in RESULTS], "matches")
    db.write("CALL db.awaitIndexes(60)")
    ingest.derive_beat(db)
    yield db
    db.write(CLEANUP)


def test_beat_aggregates_played_wins_only(mini_graph):
    """A beat B twice; D's walkover over C creates no BEAT."""
    rows = mini_graph.read(
        """
        MATCH (w:Player)-[b:BEAT]->(l:Player)
        WHERE w.id IN [-11, -12, -13, -14]
        RETURN w.id AS w, l.id AS l, b.wins AS wins, b.firstWin AS firstWin
        ORDER BY w DESC, l DESC
        """
    )
    edges = {(r["w"], r["l"]): r["wins"] for r in rows}
    assert edges == {(A, B): 2, (B, A): 1, (B, C): 1, (C, A): 1, (C, D): 1}
    assert rows[0]["firstWin"] == date(2000, 1, 1)


def test_search_finds_folded_prefixes(mini_graph):
    """Full-text search matches every word as a prefix."""
    page = players.search(mini_graph, "testpl alp", page=1, size=5)
    assert [hit.id for hit in page.items] == [A]


def test_profile_aggregates(mini_graph):
    """A: 4 matches, 2 wins, 2 losses, 1 title (final of match 1), per-surface split."""
    profile = players.profile(mini_graph, A)
    assert (profile.matches, profile.wins, profile.losses, profile.titles) == (4, 2, 2, 1)
    by_surface = {s.surface: (s.wins, s.losses) for s in profile.bySurface}
    assert by_surface == {"Clay": (1, 1), "Grass": (1, 0), "Hard": (0, 1)}


def test_matches_page_and_filters(mini_graph):
    """Most recent first, paginated, filtered by surface; the opponent is the other player."""
    page = players.matches(mini_graph, A, {}, page=1, size=2)
    assert page.total == 4 and [m.matchId for m in page.items] == ["TESTG-T-5", "TESTG-T-3"]
    clay = players.matches(mini_graph, A, {"surface": "Clay"}, page=1, size=10)
    assert {m.opponent.id for m in clay.items} == {B} and clay.total == 2


def test_head_to_head(mini_graph):
    """A leads B 2-1; one entry per surface."""
    h2h = graph.head_to_head(mini_graph, A, B)
    assert (h2h.player1Wins, h2h.player2Wins) == (2, 1)
    assert [(s.surface, s.player1Wins, s.player2Wins) for s in h2h.bySurface] == [("Clay", 1, 1), ("Grass", 1, 0)]


def test_nemesis_ranking_and_triangle(mini_graph):
    """C (1-0 over A) ranks above B (1-2); the A > B > C > A triangle is found with its records."""
    report = graph.nemesis(mini_graph, A, {"minWins": 1, "triangles": 5}, page=1, size=10)
    assert [n.opponent.id for n in report.nemeses.items] == [C, B]
    assert report.triangleCount == 1
    triangle = report.triangles[0]
    assert (triangle.second.id, triangle.third.id) == (B, C)
    assert (triangle.record, triangle.weakestLead) == (["2-1", "1-0", "1-0"], 1)


def test_beat_chain(mini_graph):
    """A > B > C is the shortest chain from A to C; each hop is backed by a played match."""
    chain = graph.beat_chain(mini_graph, A, C, max_hops=3)
    assert chain.hops == 2
    assert [(h.winner.id, h.loser.id) for h in chain.chain] == [(A, B), (B, C)]
    assert chain.chain[0].matchId == "TESTG-T-2"  # latest of A's two wins over B


def test_beat_chain_bounds_and_missing(mini_graph):
    """D beat nobody on court, so no chain; a 2-hop chain is refused under max_hops=1."""
    with pytest.raises(NotFoundError, match="No beat chain"):
        graph.beat_chain(mini_graph, D, A, max_hops=6)
    with pytest.raises(NotFoundError, match="at most 1 hops"):
        graph.beat_chain(mini_graph, A, C, max_hops=1)
    with pytest.raises(NotFoundError, match="No player"):
        graph.beat_chain(mini_graph, A, -999, max_hops=3)
    with pytest.raises(InvalidRequestError):
        graph.beat_chain(mini_graph, A, A, max_hops=3)
