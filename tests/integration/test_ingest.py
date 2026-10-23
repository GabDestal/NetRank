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

BOOKMAKER = [{"code": "TST", "name": "TEST Book"}]
PRICE = [{"matchId": "TEST-T-1", "bookmaker": "TEST Book", "winnerOdds": 1.5, "loserOdds": 2.6, "overround": 0.0513}]
MARKET = [{"matchId": "TEST-T-1", "marketMaxWinnerOdds": 1.6, "oddsLinkMethod": "exact", "oddsDayOffset": 6}]

CLEANUP = """
MATCH (n)
WHERE (n:Player AND n.id < 0) OR ((n:Match OR n:Tournament) AND n.id STARTS WITH 'TEST-')
   OR (n:Bookmaker AND n.name STARTS WITH 'TEST')
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
        ingest.load(neo4j_client, ingest.MERGE_BOOKMAKERS, BOOKMAKER, "bookmakers")
        ingest.load(neo4j_client, ingest.MERGE_PRICES, PRICE, "prices")
        ingest.load(neo4j_client, ingest.SET_MARKET, MARKET, "market odds")
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
    row = loaded.read("""
        MATCH (m:Match {id: 'TEST-T-1'})
        RETURN COUNT { (:Player)-[:WON]->(m) } AS won,
               COUNT { (:Player)-[:LOST]->(m) } AS lost,
               COUNT { (m)-[:PART_OF]->(:Tournament) } AS partOf
        """)[0]
    assert row == {"won": 1, "lost": 1, "partOf": 1}


def test_side_properties_land_on_the_relationships(loaded):
    """Each player's match stats sit on their own WON / LOST relationship."""
    row = loaded.read("""
        MATCH (w:Player)-[won:WON]->(m:Match {id: 'TEST-T-1'})<-[lost:LOST]-(l:Player)
        RETURN w.name AS winner, won.aces AS winnerAces, l.name AS loser, lost.rank AS loserRank,
               m.date AS date
        """)[0]
    assert row["winner"] == "TEST Winner" and row["winnerAces"] == 9
    assert row["loser"] == "TEST Loser" and row["loserRank"] == 40
    assert row["date"] == date(2000, 1, 3)  # converted to a Python date by the client


def test_prices_and_market_odds_attach_to_the_match(loaded):
    """One PRICED per bookmaker and match (even after reloading); market odds and provenance on Match."""
    row = loaded.read("""
        MATCH (m:Match {id: 'TEST-T-1'})
        RETURN COUNT { (:Bookmaker {name: 'TEST Book'})-[:PRICED]->(m) } AS prices,
               [(b:Bookmaker)-[p:PRICED]->(m) | p.winnerOdds][0] AS winnerOdds,
               m.marketMaxWinnerOdds AS marketMax, m.oddsLinkMethod AS method, m.oddsDayOffset AS offset
        """)[0]
    assert row == {"prices": 1, "winnerOdds": 1.5, "marketMax": 1.6, "method": "exact", "offset": 6}


def test_duplicate_player_id_is_rejected(loaded):
    """The uniqueness constraint blocks a second Player with the same id."""
    with pytest.raises(Exception, match="already exists"):
        loaded.write("CREATE (:Player {id: -1, name: 'TEST dup'})")
