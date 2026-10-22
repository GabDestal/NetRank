"""Player search, profile and match history."""

import re

from app.database.client import Neo4jClient
from app.errors import NotFoundError
from app.models.common import Page
from app.models.players import PlayerHit, PlayerMatch, PlayerProfile, SurfaceRecord
from app.text import fold

# Full-text index lookup (Lucene). Wildcard terms all score the same, so ties are broken by career
# length (a degree count read from the node, no traversal): 'feder' ranks Roger Federer before
# Federico Browne. Hits are few, so they are collected once and sliced for the page; the cost
# grows with the number of hits, not with the size of the graph.
SEARCH = """
CALL db.index.fulltext.queryNodes('player_name_ft', $query) YIELD node, score
WITH node, score, COUNT { (node)-[:WON|LOST]->() } AS matches
ORDER BY score DESC, matches DESC, node.name
WITH collect(node {.id, .name, .ioc, .hand, .dob, score: score}) AS hits
RETURN size(hits) AS total, hits[$skip..$skip + $limit] AS items
"""

# One unique-index seek on Player.id, then two subqueries over that player's matches only
# (bounded by career length, ~1,500 at most). Conditional counting in one pass avoids an
# OPTIONAL MATCH per measure, which would multiply rows.
PROFILE = """
MATCH (p:Player {id: $id})
CALL (p) {
  MATCH (p)-[r:WON|LOST]->(m:Match)
  RETURN count(m) AS matches,
         count(CASE WHEN type(r) = 'WON' AND NOT m.walkover THEN 1 END) AS wins,
         count(CASE WHEN type(r) = 'LOST' AND NOT m.walkover THEN 1 END) AS losses,
         count(CASE WHEN type(r) = 'WON' AND m.round = 'F' THEN 1 END) AS titles,
         min(r.rank) AS bestRank, min(m.date) AS firstMatch, max(m.date) AS lastMatch
}
CALL (p) {
  MATCH (p)-[r:WON|LOST]->(m:Match)
  WHERE NOT m.walkover AND m.surface IS NOT NULL
  WITH m.surface AS surface,
       count(CASE WHEN type(r) = 'WON' THEN 1 END) AS wins,
       count(CASE WHEN type(r) = 'LOST' THEN 1 END) AS losses
  ORDER BY wins + losses DESC
  RETURN collect({surface: surface, wins: wins, losses: losses}) AS bySurface
}
RETURN p {.id, .name, .ioc, .hand, .dob, .height, .wikidataId} AS player,
       matches, wins, losses, titles, bestRank, firstMatch, lastMatch, bySurface
"""

# Anchored on the player, so filters apply to that player's matches only (no global date scan).
# The page is cut before the per-match lookups (tournament, opponent, odds), which therefore run
# for at most $limit matches whatever the career length.
MATCHES = """
MATCH (p:Player {id: $id})-[r:WON|LOST]->(m:Match)
WHERE ($surface IS NULL OR m.surface = $surface)
  AND ($since IS NULL OR m.date >= $since)
  AND ($until IS NULL OR m.date <= $until)
WITH p, r, m
ORDER BY m.date DESC, m.id DESC
WITH p, collect({won: type(r) = 'WON', m: m}) AS rows
CALL (p, rows) {
  UNWIND rows[$skip..$skip + $limit] AS row
  WITH p, row.won AS won, row.m AS m
  MATCH (m)-[:PART_OF]->(t:Tournament)
  MATCH (m)<-[:WON|LOST]-(o:Player)
  WHERE o <> p
  RETURN collect({
    matchId: m.id, date: m.date, tournament: t.name, tournamentId: t.id, level: t.levelName,
    surface: m.surface, round: m.round, result: CASE WHEN won THEN 'W' ELSE 'L' END,
    score: m.score, walkover: m.walkover, retired: m.retired,
    opponent: o {.id, .name, .ioc, .hand, .dob},
    odds: [(b:Bookmaker)-[pr:PRICED]->(m) | {
      bookmaker: b.name,
      playerOdds: CASE WHEN won THEN pr.winnerOdds ELSE pr.loserOdds END,
      opponentOdds: CASE WHEN won THEN pr.loserOdds ELSE pr.winnerOdds END
    }]
  }) AS items
}
RETURN size(rows) AS total, items
"""

PLAYER_EXISTS = "MATCH (p:Player {id: $id}) RETURN p.id AS id"


def lucene_query(text: str) -> str:
    """Turn free text into a Lucene query: every word as a prefix ('rog fed' -> 'rog* AND fed*').

    Words are folded first because Lucene does not analyse wildcard terms. Only letters and digits
    survive, so user input cannot inject Lucene syntax.
    """
    words = re.findall(r"[a-z0-9]+", fold(text))
    return " AND ".join(f"{word}*" for word in words)


def search(db: Neo4jClient, text: str, page: int, size: int) -> Page[PlayerHit]:
    """Players whose name matches every word of `text` as a prefix, best match first."""
    query = lucene_query(text)
    if not query:
        return Page[PlayerHit](items=[], page=page, size=size, total=0)
    row = db.read(SEARCH, {"query": query, "skip": (page - 1) * size, "limit": size})[0]
    return Page[PlayerHit](items=row["items"], page=page, size=size, total=row["total"])


def profile(db: Neo4jClient, player_id: int) -> PlayerProfile:
    """Biography and career aggregates; raises NotFoundError for an unknown id."""
    rows = db.read(PROFILE, {"id": player_id})
    if not rows:
        raise NotFoundError(f"No player with id {player_id}")
    row = rows[0]
    by_surface = [
        SurfaceRecord(**s, winRate=round(s["wins"] / (s["wins"] + s["losses"]), 4)) for s in row["bySurface"]
    ]
    return PlayerProfile(
        **row["player"],
        matches=row["matches"],
        wins=row["wins"],
        losses=row["losses"],
        titles=row["titles"],
        bestRank=row["bestRank"],
        firstMatch=row["firstMatch"],
        lastMatch=row["lastMatch"],
        bySurface=by_surface,
    )


def ensure_player(db: Neo4jClient, player_id: int) -> None:
    """Raise NotFoundError unless the player exists (one unique-index seek)."""
    if not db.read(PLAYER_EXISTS, {"id": player_id}):
        raise NotFoundError(f"No player with id {player_id}")


def matches(db: Neo4jClient, player_id: int, filters: dict, page: int, size: int) -> Page[PlayerMatch]:
    """A player's matches, most recent first. `filters` may hold surface, since and until."""
    params = {
        "id": player_id,
        "surface": filters.get("surface"),
        "since": filters.get("since"),
        "until": filters.get("until"),
        "skip": (page - 1) * size,
        "limit": size,
    }
    rows = db.read(MATCHES, params)
    if not rows:
        ensure_player(db, player_id)
        return Page[PlayerMatch](items=[], page=page, size=size, total=0)
    return Page[PlayerMatch](items=rows[0]["items"], page=page, size=size, total=rows[0]["total"])
