"""Graph-pattern queries: head-to-head, nemeses, non-transitive triangles and beat chains.

Nemeses, triangles and chains run on the derived (Player)-[:BEAT {wins}]->(Player) relationship
(decision log D32): ~67k relationships instead of 102k Match nodes with two hops each.
"""

from collections import defaultdict

from app.database.client import Neo4jClient
from app.errors import InvalidRequestError, NotFoundError
from app.models.common import Page
from app.models.graph import BeatChain, Nemesis, NemesisReport
from app.models.players import HeadToHead

MAX_HOPS = 6

# Two unique-index seeks, then the matches between them: the pattern is anchored at both ends,
# so the cost is the smaller career, not the graph. Aggregating inside CALL keeps one row even
# when they never met.
HEAD_TO_HEAD = """
MATCH (a:Player {id: $p1})
MATCH (b:Player {id: $p2})
CALL (a, b) {
  MATCH (a)-[:WON|LOST]->(m:Match)<-[:WON|LOST]-(b)
  MATCH (w:Player)-[:WON]->(m)
  MATCH (m)-[:PART_OF]->(t:Tournament)
  WITH m, w, t
  ORDER BY m.date DESC, m.id DESC
  RETURN collect({
    matchId: m.id, date: m.date, tournament: t.name, surface: m.surface, round: m.round,
    winnerId: w.id, score: m.score, walkover: m.walkover
  }) AS matches
}
RETURN a {.id, .name, .ioc, .hand, .dob} AS player1,
       b {.id, .name, .ioc, .hand, .dob} AS player2,
       matches
"""

# Opponents with a BEAT into the player, ranked by how often they won, then by margin.
NEMESES = """
MATCH (p:Player {id: $id})
CALL (p) {
  MATCH (p)<-[nb:BEAT]-(o:Player)
  WHERE nb.wins >= $minWins
  WITH o, nb, coalesce([(p)-[pb:BEAT]->(o) | pb.wins][0], 0) AS losses
  ORDER BY nb.wins DESC, nb.wins - losses DESC, o.name
  RETURN collect({
    opponent: o {.id, .name, .ioc, .hand, .dob}, winsOverPlayer: nb.wins,
    lossesToPlayer: losses, lastWinOverPlayer: nb.lastWin
  }) AS nemeses
}
RETURN p {.id, .name, .ioc, .hand, .dob} AS player,
       size(nemeses) AS total, nemeses[$skip..$skip + $limit] AS items
"""

# p -> b -> c -> p over BEAT, then keep cycles where every edge is a strict head-to-head lead.
# Cost ~ out-degree(p) x out-degree(b) on BEAT (tens of thousands of db hits for the busiest
# players), against ~10^8 when the same cycle is matched through Match nodes.
TRIANGLES = """
MATCH (p:Player {id: $id})-[pb:BEAT]->(b:Player)-[bc:BEAT]->(c:Player)-[cp:BEAT]->(p)
WHERE b <> c
WITH p, b, c, pb.wins AS pbW, bc.wins AS bcW, cp.wins AS cpW,
     coalesce([(b)-[x:BEAT]->(p) | x.wins][0], 0) AS pbL,
     coalesce([(c)-[x:BEAT]->(b) | x.wins][0], 0) AS bcL,
     coalesce([(p)-[x:BEAT]->(c) | x.wins][0], 0) AS cpL
WHERE pbW > pbL AND bcW > bcL AND cpW > cpL
WITH b, c, [pbW - pbL, bcW - bcL, cpW - cpL] AS leads,
     [toString(pbW) + '-' + toString(pbL), toString(bcW) + '-' + toString(bcL),
      toString(cpW) + '-' + toString(cpL)] AS record
WITH b, c, record, reduce(low = leads[0], lead IN leads | CASE WHEN lead < low THEN lead ELSE low END) AS weakest
ORDER BY weakest DESC, b.name, c.name
WITH collect({
  second: b {.id, .name, .ioc, .hand, .dob}, third: c {.id, .name, .ioc, .hand, .dob},
  record: record, weakestLead: weakest
}) AS triangles
RETURN size(triangles) AS total, triangles[0..$limit] AS items
"""

# SHORTEST 1 explores BEAT breadth-first from the source and stops at the first hit; the
# quantifier caps the search at MAX_HOPS (a literal: quantifier bounds cannot be parameters),
# and $maxHops then rejects longer chains. Each hop is backed by the latest played win.
BEAT_CHAIN = """
MATCH (s:Player {id: $source})
MATCH (t:Player {id: $target})
OPTIONAL MATCH found = SHORTEST 1 (s)-[:BEAT]->{1,6}(t)
WITH s, t, CASE WHEN length(found) <= $maxHops THEN found END AS path
CALL (path) {
  UNWIND CASE WHEN path IS NULL THEN [] ELSE range(0, length(path) - 1) END AS i
  WITH i, relationships(path)[i] AS beat
  WITH i, beat, startNode(beat) AS w, endNode(beat) AS l
  CALL (w, l) {
    MATCH (w)-[:WON]->(m:Match)<-[:LOST]-(l)
    WHERE NOT m.walkover
    MATCH (m)-[:PART_OF]->(tr:Tournament)
    RETURN m, tr
    ORDER BY m.date DESC
    LIMIT 1
  }
  WITH i, beat, w, l, m, tr
  ORDER BY i
  RETURN collect({
    winner: w {.id, .name, .ioc, .hand, .dob}, loser: l {.id, .name, .ioc, .hand, .dob},
    wins: beat.wins, matchId: m.id, date: m.date, tournament: tr.name, round: m.round, score: m.score
  }) AS chain
}
RETURN s {.id, .name, .ioc, .hand, .dob} AS source,
       t {.id, .name, .ioc, .hand, .dob} AS target,
       path IS NOT NULL AS found, chain
"""


def head_to_head(db: Neo4jClient, p1: int, p2: int) -> HeadToHead:
    """Every meeting between two players with overall and per-surface records."""
    if p1 == p2:
        raise InvalidRequestError("p1 and p2 must be different players")
    rows = db.read(HEAD_TO_HEAD, {"p1": p1, "p2": p2})
    if not rows:
        raise NotFoundError(f"No player with id {p1} or {p2}")
    row = rows[0]
    played = [m for m in row["matches"] if not m["walkover"]]
    by_surface: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for match in played:
        by_surface[match["surface"] or "Unknown"][0 if match["winnerId"] == p1 else 1] += 1
    return HeadToHead(
        player1=row["player1"],
        player2=row["player2"],
        player1Wins=sum(m["winnerId"] == p1 for m in played),
        player2Wins=sum(m["winnerId"] == p2 for m in played),
        bySurface=[{"surface": s, "player1Wins": w[0], "player2Wins": w[1]} for s, w in sorted(by_surface.items())],
        matches=row["matches"],
    )


def nemesis(db: Neo4jClient, player_id: int, options: dict, page: int, size: int) -> NemesisReport:
    """Nemeses (paginated) and the strongest non-transitive triangles through a player.

    `options`: minWins (int, opponents need at least that many wins) and triangles (how many to return).
    """
    params = {"id": player_id, "minWins": options["minWins"], "skip": (page - 1) * size, "limit": size}
    rows = db.read(NEMESES, params)
    if not rows:
        raise NotFoundError(f"No player with id {player_id}")
    triangles = db.read(TRIANGLES, {"id": player_id, "limit": options["triangles"]})[0]
    return NemesisReport(
        player=rows[0]["player"],
        nemeses=Page[Nemesis](items=rows[0]["items"], page=page, size=size, total=rows[0]["total"]),
        triangleCount=triangles["total"],
        triangles=triangles["items"],
    )


def beat_chain(db: Neo4jClient, source: int, target: int, max_hops: int) -> BeatChain:
    """Shortest chain source > ... > target (each beat the next) of at most `max_hops` hops."""
    if source == target:
        raise InvalidRequestError("from and to must be different players")
    rows = db.read(BEAT_CHAIN, {"source": source, "target": target, "maxHops": max_hops})
    if not rows:
        raise NotFoundError(f"No player with id {source} or {target}")
    row = rows[0]
    if not row["found"]:
        raise NotFoundError(f"No beat chain of at most {max_hops} hops from {source} to {target}")
    return BeatChain(source=row["source"], target=row["target"], hops=len(row["chain"]), chain=row["chain"])
