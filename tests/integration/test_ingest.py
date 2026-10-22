"""Cypher tests for the schema and the ingestion queries, on throwaway TEST- records."""

from datetime import date

import pytest

from scripts import ingest

pytestmark = pytest.mark.integration

PLAYERS = [{"id": -1, "name": "TEST Winner"}, {"id": -2, "name": "TEST Loser"}]
TOURNAMENT = [{"id": "TEST-T", "name": "TEST Open", "year": 2000, "level": "A", "surface": "Hard"}]
MATCH = {
    "id": "TEST-T-1",
    "tournamentId": "TEST-T",
    "date": date(2000, 1, 3),
    "round": "F",
    "bestOf": 3,
    "score": "6-4 6-4",
    "minutes": 80,
    "surface": "Hard",
    "walkover": False,
    "retired": False,
    "winnerId": -1,
    "loserId": -2,
    "winner": {"aces": 9, "rank": 3},
    "loser": {"aces": 2, "rank": 40},
}

CLEANUP = """
MATCH (n) WHERE (n:Player AND n.id < 0) OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TEST-')
DETACH DELETE n
"""


@pytest.fixture(name="loaded")
def fixture_loaded(neo4j_client):
    """Schema plus one test match, loaded twice to prove idempotency; removed afterwards."""
    ingest.ensure_schema(neo4j_client)
    for _ in range(2):
        ingest.load(neo4j_client, ingest.MERGE_PLAYERS, PLAYERS, "players")
        ingest.load(neo4j_client, ingest.MERGE_TOURNAMENTS, TOURNAMENT, "tournaments")
        ingest.load(neo4j_client, ingest.MERGE_MATCHES, [MATCH], "matches")
    yield neo4j_client
    neo4j_client.write(CLEANUP)


def test_constraints_and_indexes_exist(loaded):
    """The four uniqueness constraints and the two range indexes are in place."""
    constraints = {row["name"] for row in loaded.read("SHOW CONSTRAINTS YIELD name")}
    indexes = {row["name"] for row in loaded.read("SHOW INDEXES YIELD name")}
    assert {"player_id", "match_id", "tournament_id", "bookmaker_name"} <= constraints
    assert {"match_date", "player_name"} <= indexes


def test_match_is_linked_once_despite_reloading(loaded):
    """Two loads produce exactly one WON, one LOST and one PART_OF."""
    row = loaded.read(
        """
        MATCH (m:Match {id: 'TEST-T-1'})
        RETURN COUNT { (:Player)-[:WON]->(m) } AS won,
               COUNT { (:Player)-[:LOST]->(m) } AS lost,
               COUNT { (m)-[:PART_OF]->(:Tournament) } AS partOf
        """
    )[0]
    assert row == {"won": 1, "lost": 1, "partOf": 1}


def test_side_properties_land_on_the_relationships(loaded):
    """Each player's match stats sit on their own WON / LOST relationship."""
    row = loaded.read(
        """
        MATCH (w:Player)-[won:WON]->(m:Match {id: 'TEST-T-1'})<-[lost:LOST]-(l:Player)
        RETURN w.name AS winner, won.aces AS winnerAces, l.name AS loser, lost.rank AS loserRank,
               m.date AS date
        """
    )[0]
    assert row["winner"] == "TEST Winner" and row["winnerAces"] == 9
    assert row["loser"] == "TEST Loser" and row["loserRank"] == 40
    assert row["date"].to_native() == date(2000, 1, 3)


def test_duplicate_player_id_is_rejected(loaded):
    """The uniqueness constraint blocks a second Player with the same id."""
    with pytest.raises(Exception, match="already exists"):
        loaded.write("CREATE (:Player {id: -1, name: 'TEST dup'})")
