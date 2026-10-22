"""Create the Neo4j schema and load the graph from the raw files.

Idempotent: every write is a MERGE on a uniquely constrained key, so re-running updates in place.

Usage: python -m scripts.ingest
"""

import logging
from collections.abc import Iterator

from app.config import get_settings
from app.database.client import Neo4jClient
from scripts import sackmann

BATCH_SIZE = 2000

SCHEMA = [
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT match_id IF NOT EXISTS FOR (m:Match) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT tournament_id IF NOT EXISTS FOR (t:Tournament) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT bookmaker_name IF NOT EXISTS FOR (b:Bookmaker) REQUIRE b.name IS UNIQUE",
    "CREATE INDEX match_date IF NOT EXISTS FOR (m:Match) ON (m.date)",
    "CREATE INDEX player_name IF NOT EXISTS FOR (p:Player) ON (p.name)",
]

MERGE_PLAYERS = """
UNWIND $rows AS row
MERGE (p:Player {id: row.id})
SET p += row
"""

MERGE_TOURNAMENTS = """
UNWIND $rows AS row
MERGE (t:Tournament {id: row.id})
SET t += row
"""

# One row per match. Each MATCH below hits a unique-constraint index, so a row costs a few index
# seeks regardless of graph size; there is no Cartesian product across rows.
MERGE_MATCHES = """
UNWIND $rows AS row
MATCH (t:Tournament {id: row.tournamentId})
MATCH (w:Player {id: row.winnerId})
MATCH (l:Player {id: row.loserId})
MERGE (m:Match {id: row.id})
SET m.date = row.date, m.round = row.round, m.bestOf = row.bestOf, m.score = row.score,
    m.minutes = row.minutes, m.surface = row.surface, m.walkover = row.walkover, m.retired = row.retired
MERGE (m)-[:PART_OF]->(t)
MERGE (w)-[won:WON]->(m)
SET won += row.winner
MERGE (l)-[lost:LOST]->(m)
SET lost += row.loser
"""

COUNTS = """
CALL () { MATCH (p:Player) RETURN count(p) AS players }
CALL () { MATCH (t:Tournament) RETURN count(t) AS tournaments }
CALL () { MATCH (m:Match) RETURN count(m) AS matches }
CALL () { MATCH ()-[r:WON]->() RETURN count(r) AS won }
CALL () { MATCH ()-[r:LOST]->() RETURN count(r) AS lost }
RETURN players, tournaments, matches, won, lost
"""

log = logging.getLogger(__name__)


def batches(rows: list[dict], size: int = BATCH_SIZE) -> Iterator[list[dict]]:
    """Yield consecutive slices of at most `size` rows."""
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def load(db: Neo4jClient, query: str, rows: list[dict], label: str) -> None:
    """Run a parameterised UNWIND query over `rows` in batches."""
    for batch in batches(rows):
        db.write(query, {"rows": batch})
    log.info(f"{label}: {len(rows)} rows merged")


def ensure_schema(db: Neo4jClient) -> None:
    """Create constraints and indexes if they do not exist yet."""
    for statement in SCHEMA:
        db.write(statement)


def load_sackmann(db: Neo4jClient) -> None:
    """Load players, tournament editions and matches from the Sackmann files."""
    matches = sackmann.read_matches()
    players = sackmann.read_players()
    remap = sackmann.canonical_ids(players, matches)
    match_rows = sackmann.match_records(matches, remap)
    player_ids = {row["winnerId"] for row in match_rows} | {row["loserId"] for row in match_rows}

    load(db, MERGE_PLAYERS, sackmann.player_records(players, player_ids), "players")
    load(db, MERGE_TOURNAMENTS, sackmann.tournament_records(matches), "tournaments")
    load(db, MERGE_MATCHES, match_rows, "matches")


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Neo4jClient.from_settings(get_settings())
    try:
        ensure_schema(db)
        load_sackmann(db)
        log.info(f"graph: {db.read(COUNTS)[0]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
