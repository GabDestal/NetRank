"""Graph Data Science computations: prestige (PageRank), style similarity (KNN), styles (Louvain), FastRP.

Lifecycle (decision log D43): the GDS catalog is in memory and lost on restart, so nothing the API
reads lives there. `refresh` projects, computes and WRITES results to the database (Player
properties and SIMILAR_STYLE relationships), then drops its projections. The only per-request
projection is era PageRank, built from Match in the requested window, streamed, cached and dropped.
"""

import logging
import statistics
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from neo4j.exceptions import ClientError

from app.config import get_settings
from app.database.client import Neo4jClient
from app.errors import GdsUnavailableError, NotFoundError

SEED = 42
KNN_TOP_K = 10
FASTRP_DIMENSION = 64
BEAT_GRAPH = "netrank-beat"
STYLE_GRAPH = "netrank-style"
ERA_CACHE_SIZE = 32

FEATURES = (
    "acePct",
    "doubleFaultPct",
    "firstServeInPct",
    "firstServeWonPct",
    "secondServeWonPct",
    "breakPointsSavedPct",
    "returnPointsWonPct",
    "breakPointsConvertedPct",
    "clayWinShare",
    "grassWinShare",
    "hardWinShare",
)

DROP_GRAPH = "CALL gds.graph.drop($graph, false) YIELD graphName RETURN graphName"

# --- All-time prestige: native projection of BEAT, reversed, so each edge points loser -> winner
# and carries the number of wins. PageRank then flows prestige towards players who beat players
# who themselves beat many others.
PROJECT_BEAT = """
CALL gds.graph.project($graph, 'Player', {LOST_TO: {type: 'BEAT', orientation: 'REVERSE', properties: 'wins'}})
YIELD nodeCount, relationshipCount
RETURN nodeCount, relationshipCount
"""

PAGERANK_WRITE = """
CALL gds.pageRank.write($graph, {
  relationshipWeightProperty: 'wins', dampingFactor: 0.85, maxIterations: 100, tolerance: 1.0e-7,
  writeProperty: 'prestige', concurrency: $concurrency
})
YIELD nodePropertiesWritten, ranIterations, didConverge
RETURN nodePropertiesWritten, ranIterations, didConverge
"""

PRESTIGE_RANK = """
MATCH (p:Player)
WHERE p.prestige IS NOT NULL
WITH p
ORDER BY p.prestige DESC, p.id
WITH collect(p) AS ranked
UNWIND range(0, size(ranked) - 1) AS i
WITH ranked[i] AS p, i + 1 AS rank
SET p.prestigeRank = rank
RETURN count(*) AS ranked
"""

# --- Era prestige: Cypher-aggregation projection over Match inside [start, end) (decision log D40).
# The Match.date range index bounds the scan to the window; BEAT cannot be used because its wins
# are career totals.
PROJECT_ERA = """
MATCH (w:Player)-[:WON]->(m:Match)<-[:LOST]-(l:Player)
WHERE ($start IS NULL OR m.date >= $start) AND m.date < $end AND NOT m.walkover
WITH l, w, count(m) AS wins
WITH gds.graph.project($graph, l, w, {relationshipProperties: {wins: toFloat(wins)}}) AS g
RETURN g.nodeCount AS nodeCount, g.relationshipCount AS relationshipCount
"""

PAGERANK_STREAM = """
CALL gds.pageRank.stream($graph, {
  relationshipWeightProperty: 'wins', dampingFactor: 0.85, maxIterations: 100, tolerance: 1.0e-7,
  concurrency: $concurrency
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS id, score
ORDER BY score DESC, id
"""

# --- Style features (decision log D41): career serve/return percentages from the per-player
# stats on WON/LOST (own side r, opponent side o), plus the share of wins on each surface.
STYLE_STATS = """
MATCH (p:Player)
CALL (p) {
  MATCH (p)-[r:WON|LOST]->(m:Match)<-[o:WON|LOST]-(:Player)
  WHERE NOT m.walkover AND r.servePoints > 0 AND o.servePoints > 0
  RETURN count(m) AS matches,
         sum(r.aces) AS aces, sum(r.doubleFaults) AS doubleFaults, sum(r.servePoints) AS servePoints,
         sum(r.firstServesIn) AS firstIn, sum(r.firstServeWon) AS firstWon, sum(r.secondServeWon) AS secondWon,
         sum(r.breakPointsSaved) AS bpSaved, sum(r.breakPointsFaced) AS bpFaced,
         sum(o.servePoints) AS oppServePoints, sum(o.firstServeWon + o.secondServeWon) AS oppServeWon,
         sum(o.breakPointsFaced) AS oppBpFaced, sum(o.breakPointsSaved) AS oppBpSaved
}
WITH p, matches, aces, doubleFaults, servePoints, firstIn, firstWon, secondWon, bpSaved, bpFaced,
     oppServePoints, oppServeWon, oppBpFaced, oppBpSaved
WHERE matches >= $minMatches
CALL (p) {
  MATCH (p)-[:WON]->(m:Match)
  WHERE NOT m.walkover
  RETURN count(m) AS wins,
         count(CASE WHEN m.surface = 'Clay' THEN 1 END) AS clayWins,
         count(CASE WHEN m.surface = 'Grass' THEN 1 END) AS grassWins,
         count(CASE WHEN m.surface = 'Hard' THEN 1 END) AS hardWins
}
RETURN p.id AS id, matches, aces, doubleFaults, servePoints, firstIn, firstWon, secondWon, bpSaved, bpFaced,
       oppServePoints, oppServeWon, oppBpFaced, oppBpSaved, wins, clayWins, grassWins, hardWins
ORDER BY id
"""

CLEAR_STYLE = """
MATCH (p:Player)
WHERE p.styleVector IS NOT NULL OR p.styleId IS NOT NULL
SET p += $cleared
RETURN count(p) AS cleared
"""

WRITE_STYLE = """
UNWIND $rows AS row
MATCH (p:Player {id: row.id})
SET p += row.props
"""

DELETE_SIMILAR_BATCH = """
MATCH ()-[s:SIMILAR_STYLE]->()
WITH s LIMIT 20000
DELETE s
RETURN count(*) AS deleted
"""

PROJECT_STYLE = """
MATCH (p:Player)
WHERE p.styleVector IS NOT NULL
WITH gds.graph.project($graph, p, null, {sourceNodeProperties: p {.styleVector}, targetNodeProperties: null}) AS g
RETURN g.nodeCount AS nodeCount
"""

KNN_MUTATE = """
CALL gds.knn.mutate($graph, {
  nodeProperties: {styleVector: 'COSINE'}, topK: $topK, randomSeed: $seed, concurrency: 1,
  sampleRate: 1.0, deltaThreshold: 0.0,
  mutateRelationshipType: 'SIMILAR_STYLE', mutateProperty: 'score'
})
YIELD relationshipsWritten, nodesCompared
RETURN relationshipsWritten, nodesCompared
"""

PERSIST_SIMILAR = """
CALL gds.graph.relationship.write($graph, 'SIMILAR_STYLE', 'score')
YIELD relationshipsWritten
RETURN relationshipsWritten
"""

TO_UNDIRECTED = """
CALL gds.graph.relationships.toUndirected($graph, {
  relationshipType: 'SIMILAR_STYLE', mutateRelationshipType: 'SIMILAR_STYLE_UNDIRECTED', aggregation: 'MAX'
})
YIELD relationshipsWritten
RETURN relationshipsWritten
"""

LOUVAIN_WRITE = """
CALL gds.louvain.write($graph, {
  relationshipTypes: ['SIMILAR_STYLE_UNDIRECTED'], relationshipWeightProperty: 'score',
  writeProperty: 'styleCommunity', concurrency: 1
})
YIELD communityCount, modularity, ranLevels
RETURN communityCount, modularity, ranLevels
"""

# Louvain community ids are internal node ids; renumber 1..k by size (largest first) so ids are
# small and stable for a given result.
NUMBER_STYLES = """
MATCH (p:Player)
WHERE p.styleCommunity IS NOT NULL
WITH p.styleCommunity AS community, count(*) AS size
ORDER BY size DESC, community
WITH collect(community) AS communities
UNWIND range(0, size(communities) - 1) AS i
MATCH (p:Player {styleCommunity: communities[i]})
SET p.styleId = i + 1
REMOVE p.styleCommunity
RETURN count(DISTINCT i) AS styles
"""

# --- FastRP with a cutoff (decision log D42): only matches strictly before the cutoff are projected,
# undirected and weighted by wins, so embeddings used as ML features cannot see the future.
PROJECT_BEFORE = """
MATCH (w:Player)-[:WON]->(m:Match)<-[:LOST]-(l:Player)
WHERE m.date < $cutoff AND NOT m.walkover
WITH w, l, count(m) AS wins
WITH gds.graph.project($graph, w, l, {relationshipProperties: {wins: toFloat(wins)}},
                       {undirectedRelationshipTypes: ['*']}) AS g
RETURN g.nodeCount AS nodeCount
"""

FASTRP_STREAM = """
CALL gds.fastRP.stream($graph, {
  embeddingDimension: $dimension, randomSeed: $seed, concurrency: $concurrency,
  relationshipWeightProperty: 'wins', iterationWeights: [0.0, 1.0, 1.0]
})
YIELD nodeId, embedding
RETURN gds.util.asNode(nodeId).id AS id, embedding
"""

log = logging.getLogger(__name__)
_era_cache: OrderedDict[tuple[int, int], list[dict]] = OrderedDict()
_era_lock = threading.Lock()


def gds_call(db: Neo4jClient, query: str, params: dict | None = None) -> list[dict]:
    """Run a GDS query; a server-side GDS failure becomes GdsUnavailableError (HTTP 503)."""
    try:
        return db.write(query, params or {})
    except ClientError as exc:
        raise GdsUnavailableError(f"GDS call failed ({exc.code})") from exc


@contextmanager
def projection(db: Neo4jClient, prefix: str) -> Iterator[str]:
    """A unique in-memory graph name, dropped on exit even if the computation fails."""
    name = f"{prefix}-{uuid.uuid4().hex[:12]}"
    try:
        yield name
    finally:
        try:
            db.write(DROP_GRAPH, {"graph": name})
        except ClientError:
            log.warning(f"could not drop projection {name}")


def concurrency() -> int:
    """Configured GDS concurrency (1 in tests for reproducible results)."""
    return get_settings().gds_concurrency


# --------------------------------------------------------------------------- era PageRank


def pagerank_window(db: Neo4jClient, start: date | None, end: date) -> list[dict]:
    """PageRank over played matches dated in [start, end) (no lower bound when start is None).

    Best first: [{id, score}]; empty when the window holds no played match. Not cached.
    """
    with projection(db, "netrank-window") as graph:
        projected = gds_call(db, PROJECT_ERA, {"start": start, "end": end, "graph": graph})
        if not projected or not projected[0]["nodeCount"]:
            return []
        return gds_call(db, PAGERANK_STREAM, {"graph": graph, "concurrency": concurrency()})


def era_ranking(db: Neo4jClient, start_year: int, end_year: int) -> list[dict]:
    """PageRank over played matches in seasons [start_year, end_year], best first: [{id, score}].

    Cached per era for the life of the process (results only change on re-ingest; refresh clears it).
    One computation at a time, so concurrent requests cannot pile up projections.
    """
    key = (start_year, end_year)
    with _era_lock:
        if key in _era_cache:
            _era_cache.move_to_end(key)
            return _era_cache[key]
        ranking = pagerank_window(db, date(start_year, 1, 1), date(end_year + 1, 1, 1))
        if not ranking:
            raise NotFoundError(f"No played matches between {start_year} and {end_year}")
        _era_cache[key] = ranking
        if len(_era_cache) > ERA_CACHE_SIZE:
            _era_cache.popitem(last=False)
        return ranking


def clear_era_cache() -> None:
    """Forget cached era rankings (called by refresh)."""
    with _era_lock:
        _era_cache.clear()


# --------------------------------------------------------------------------- style features


def ratio(numerator: float | None, denominator: float | None) -> float:
    """numerator / denominator, 0.0 when the denominator is missing or zero."""
    return float(numerator) / float(denominator) if numerator is not None and denominator else 0.0


def style_features(row: dict) -> dict[str, float]:
    """The eleven raw style features of one player from aggregated match statistics."""
    second_serves = (row["servePoints"] or 0) - (row["firstIn"] or 0)
    return {
        "acePct": ratio(row["aces"], row["servePoints"]),
        "doubleFaultPct": ratio(row["doubleFaults"], row["servePoints"]),
        "firstServeInPct": ratio(row["firstIn"], row["servePoints"]),
        "firstServeWonPct": ratio(row["firstWon"], row["firstIn"]),
        "secondServeWonPct": ratio(row["secondWon"], second_serves),
        "breakPointsSavedPct": ratio(row["bpSaved"], row["bpFaced"]),
        "returnPointsWonPct": ratio((row["oppServePoints"] or 0) - (row["oppServeWon"] or 0), row["oppServePoints"]),
        "breakPointsConvertedPct": ratio((row["oppBpFaced"] or 0) - (row["oppBpSaved"] or 0), row["oppBpFaced"]),
        "clayWinShare": ratio(row["clayWins"], row["wins"]),
        "grassWinShare": ratio(row["grassWins"], row["wins"]),
        "hardWinShare": ratio(row["hardWins"], row["wins"]),
    }


def standardise(features: list[dict[str, float]]) -> list[list[float]]:
    """z-score every feature across players so no single scale dominates the cosine similarity."""
    columns = {name: [f[name] for f in features] for name in FEATURES}
    moments = {name: (statistics.fmean(v), statistics.pstdev(v)) for name, v in columns.items()}
    return [
        [round((f[name] - moments[name][0]) / moments[name][1], 6) if moments[name][1] else 0.0 for name in FEATURES]
        for f in features
    ]


def write_style_vectors(db: Neo4jClient, min_matches: int) -> int:
    """Compute, standardise and store style features; returns the number of players with a vector."""
    cleared = {name: None for name in (*FEATURES, "styleVector", "styleMatches", "styleId", "styleCommunity")}
    db.write(CLEAR_STYLE, {"cleared": cleared})
    rows = db.read(STYLE_STATS, {"minMatches": min_matches})
    features = [style_features(row) for row in rows]
    vectors = standardise(features) if rows else []
    payload = [
        {"id": row["id"], "props": {**{k: round(v, 6) for k, v in feats.items()}, "styleVector": vec,
                                    "styleMatches": row["matches"]}}
        for row, feats, vec in zip(rows, features, vectors)
    ]
    for start in range(0, len(payload), 1000):
        db.write(WRITE_STYLE, {"rows": payload[start : start + 1000]})
    return len(payload)


# --------------------------------------------------------------------------- refresh


def refresh_prestige(db: Neo4jClient) -> dict:
    """All-time PageRank on the native reversed-BEAT projection, written as Player.prestige(+Rank)."""
    gds_call(db, "MATCH (p:Player) WHERE p.prestige IS NOT NULL REMOVE p.prestige, p.prestigeRank")
    with projection(db, BEAT_GRAPH) as graph:
        projected = gds_call(db, PROJECT_BEAT, {"graph": graph})[0]
        result = gds_call(db, PAGERANK_WRITE, {"graph": graph, "concurrency": concurrency()})[0]
    db.write(PRESTIGE_RANK)
    return {**projected, **result}


def refresh_styles(db: Neo4jClient, min_matches: int) -> dict:
    """Style vectors -> KNN (written as SIMILAR_STYLE) -> Louvain on the undirected KNN graph -> styleId."""
    players = write_style_vectors(db, min_matches)
    while db.write(DELETE_SIMILAR_BATCH)[0]["deleted"]:
        pass
    if players < 2:
        return {"players": players, "similarRelationships": 0, "styles": 0, "modularity": None}
    with projection(db, STYLE_GRAPH) as graph:
        gds_call(db, PROJECT_STYLE, {"graph": graph})
        gds_call(db, KNN_MUTATE, {"graph": graph, "topK": KNN_TOP_K, "seed": SEED})
        written = gds_call(db, PERSIST_SIMILAR, {"graph": graph})[0]["relationshipsWritten"]
        gds_call(db, TO_UNDIRECTED, {"graph": graph})
        louvain = gds_call(db, LOUVAIN_WRITE, {"graph": graph})[0]
    styles = db.write(NUMBER_STYLES)[0]["styles"]
    return {
        "players": players,
        "similarRelationships": written,
        "styles": styles,
        "modularity": round(louvain["modularity"], 4),
    }


def refresh(db: Neo4jClient) -> dict:
    """Recompute everything the API reads from GDS and clear the era cache."""
    settings = get_settings()
    started = time.perf_counter()
    report = {
        "prestige": refresh_prestige(db),
        "styles": refresh_styles(db, settings.style_min_matches),
        "concurrency": settings.gds_concurrency,
        "minMatches": settings.style_min_matches,
    }
    clear_era_cache()
    report["seconds"] = round(time.perf_counter() - started, 2)
    log.info(f"GDS refresh: {report}")
    return report


# --------------------------------------------------------------------------- FastRP


def fastrp_embeddings(
    db: Neo4jClient, cutoff: date, dimension: int = FASTRP_DIMENSION, seed: int = SEED
) -> dict[int, list[float]]:
    """FastRP embedding per player computed only from matches played before `cutoff`.

    Players without a played match before the cutoff get no embedding.
    """
    with projection(db, "netrank-fastrp") as graph:
        projected = gds_call(db, PROJECT_BEFORE, {"graph": graph, "cutoff": cutoff})
        if not projected or not projected[0]["nodeCount"]:
            return {}
        params = {"graph": graph, "dimension": dimension, "seed": seed, "concurrency": concurrency()}
        rows = gds_call(db, FASTRP_STREAM, params)
    return {row["id"]: row["embedding"] for row in rows}
