"""Read side of the GDS results: prestige, similar players and styles.

All-time prestige, SIMILAR_STYLE and styleId are written by gds.refresh; missing results mean the
refresh has not run, which is reported as GdsUnavailableError (503). Era prestige comes from the
per-request era ranking (gds.era_ranking).
"""

import re
import statistics
from collections import defaultdict

from app.database.client import Neo4jClient
from app.errors import GdsUnavailableError, InvalidRequestError, NotFoundError
from app.models.analytics import (
    Era,
    PlayerPrestige,
    PrestigeBoard,
    PrestigeEntry,
    SimilarResult,
    StyleDetail,
    StyleMember,
    StyleSummary,
    StyleTrait,
)
from app.models.common import Page
from app.services import gds

FIRST_SEASON, LAST_SEASON = 1991, 2026
NOT_COMPUTED = "GDS results not computed yet: run POST /api/admin/gds/refresh (or make gds)"
TRAIT_THRESHOLD = 0.5
MAX_TRAITS = 3
# Readable label for a centroid well above (+) or below (-) the average styled player.
TRAIT_LABELS = {
    "acePct": ("big server", "few aces"),
    "doubleFaultPct": ("risky second serve", "safe second serve"),
    "firstServeInPct": ("high first-serve percentage", "low first-serve percentage"),
    "firstServeWonPct": ("dominant first serve", "weak first serve"),
    "secondServeWonPct": ("strong second serve", "vulnerable second serve"),
    "breakPointsSavedPct": ("saves break points", "breakable on serve"),
    "returnPointsWonPct": ("strong returner", "weak returner"),
    "breakPointsConvertedPct": ("converts break points", "wastes break points"),
    "clayWinShare": ("wins mostly on clay", "rarely wins on clay"),
    "grassWinShare": ("wins often on grass", "rarely wins on grass"),
    "hardWinShare": ("wins mostly on hard courts", "rarely wins on hard courts"),
}

ALL_TIME_PRESTIGE = """
MATCH (p:Player {id: $id})
RETURN p {.id, .name, .ioc, .hand, .dob} AS player, p.prestige AS score, p.prestigeRank AS rank,
       COUNT { (q:Player) WHERE q.prestigeRank IS NOT NULL } AS ranked
"""

ALL_TIME_BOARD = """
MATCH (p:Player)
WHERE p.prestigeRank IS NOT NULL
WITH p
ORDER BY p.prestigeRank
WITH collect({rank: p.prestigeRank, score: p.prestige, player: p {.id, .name, .ioc, .hand, .dob}}) AS ranking
RETURN size(ranking) AS total, ranking[$skip..$skip + $limit] AS items
"""

SUMMARIES = """
MATCH (p:Player)
WHERE p.id IN $ids
RETURN p {.id, .name, .ioc, .hand, .dob} AS player
"""

FEATURES_MAP = (
    "{.acePct, .doubleFaultPct, .firstServeInPct, .firstServeWonPct, .secondServeWonPct, .breakPointsSavedPct,"
    + " .returnPointsWonPct, .breakPointsConvertedPct, .clayWinShare, .grassWinShare, .hardWinShare}"
)

# KNN neighbours were written as SIMILAR_STYLE (topK per player), so this is a local expansion.
SIMILAR = (
    """
MATCH (p:Player {id: $id})
OPTIONAL MATCH (p)-[s:SIMILAR_STYLE]->(o:Player)
WITH p, s, o
ORDER BY s.score DESC, o.name
WITH p, collect(CASE WHEN o IS NULL THEN null ELSE
  {player: o {.id, .name, .ioc, .hand, .dob}, score: s.score, styleId: o.styleId, features: o """
    + FEATURES_MAP
    + """} END) AS similar
RETURN p {.id, .name, .ioc, .hand, .dob} AS player, p.styleId AS styleId, p.styleVector IS NOT NULL AS hasStyle,
       p """
    + FEATURES_MAP
    + """ AS features, size(similar) AS total, similar[$skip..$skip + $limit] AS items
"""
)

STYLE_MEMBERS = """
MATCH (p:Player)
WHERE p.styleId IS NOT NULL AND ($styleId IS NULL OR p.styleId = $styleId)
RETURN p.styleId AS styleId, p {.id, .name, .ioc, .hand, .dob} AS player, p.styleVector AS vector,
       p.prestigeRank AS prestigeRank, p.styleMatches AS matches
ORDER BY coalesce(p.prestigeRank, 1000000), p.id
"""


# --------------------------------------------------------------------------- eras


def parse_era(text: str | None) -> Era | None:
    """'2000s', '2004-2008' or '2010' -> Era; None or 'all' -> None (all-time).

    Seasons are clipped to the data (1991-2026); an empty or inverted range is a 400.
    """
    if text is None or text.strip().lower() in ("", "all", "all-time"):
        return None
    value = text.strip().lower()
    if match := re.fullmatch(r"(\d{3})0s", value):
        start, end = int(match.group(1)) * 10, int(match.group(1)) * 10 + 9
    elif match := re.fullmatch(r"(\d{4})(?:-(\d{4}))?", value):
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
    else:
        raise InvalidRequestError("era must look like '2000s', '2004-2008' or '2010'")
    start, end = max(start, FIRST_SEASON), min(end, LAST_SEASON)
    if start > end:
        raise InvalidRequestError(f"era must overlap the seasons {FIRST_SEASON}-{LAST_SEASON} and start before it ends")
    return Era(label=f"{start}-{end}" if start != end else str(start), startYear=start, endYear=end)


# --------------------------------------------------------------------------- prestige


def player_prestige(db: Neo4jClient, player_id: int, era: Era | None) -> PlayerPrestige:
    """One player's prestige score and rank, all-time (stored) or within an era (streamed, cached)."""
    if era is None:
        rows = db.read(ALL_TIME_PRESTIGE, {"id": player_id})
        if not rows:
            raise NotFoundError(f"No player with id {player_id}")
        row = rows[0]
        if row["rank"] is None:
            raise GdsUnavailableError(NOT_COMPUTED)
        return PlayerPrestige(
            player=row["player"],
            era=None,
            score=row["score"],
            rank=row["rank"],
            playersRanked=row["ranked"],
            percentile=percentile(row["rank"], row["ranked"]),
        )
    ranking = gds.era_ranking(db, era.startYear, era.endYear)
    position = next((i for i, entry in enumerate(ranking) if entry["id"] == player_id), None)
    if position is None:
        summaries = db.read(SUMMARIES, {"ids": [player_id]})
        if not summaries:
            raise NotFoundError(f"No player with id {player_id}")
        raise NotFoundError(f"{summaries[0]['player']['name']} played no tour-level match in {era.label}")
    player = db.read(SUMMARIES, {"ids": [player_id]})[0]["player"]
    return PlayerPrestige(
        player=player,
        era=era,
        score=ranking[position]["score"],
        rank=position + 1,
        playersRanked=len(ranking),
        percentile=percentile(position + 1, len(ranking)),
    )


def percentile(rank: int, total: int) -> float:
    """Share of ranked players strictly below `rank` (1 is best)."""
    return round((total - rank) / total, 4) if total else 0.0


def prestige_board(db: Neo4jClient, era: Era | None, page: int, size: int) -> PrestigeBoard:
    """Paginated prestige leaderboard, all-time or within an era."""
    skip = (page - 1) * size
    if era is None:
        row = db.read(ALL_TIME_BOARD, {"skip": skip, "limit": size})[0]
        if not row["total"]:
            raise GdsUnavailableError(NOT_COMPUTED)
        board = Page[PrestigeEntry](items=row["items"], page=page, size=size, total=row["total"])
        return PrestigeBoard(era=None, ranking=board)
    ranking = gds.era_ranking(db, era.startYear, era.endYear)
    window = ranking[skip : skip + size]
    players = {row["player"]["id"]: row["player"] for row in db.read(SUMMARIES, {"ids": [e["id"] for e in window]})}
    items = [
        PrestigeEntry(rank=skip + i + 1, player=players[entry["id"]], score=entry["score"])
        for i, entry in enumerate(window)
    ]
    return PrestigeBoard(era=era, ranking=Page[PrestigeEntry](items=items, page=page, size=size, total=len(ranking)))


# --------------------------------------------------------------------------- similarity and styles


def similar(db: Neo4jClient, player_id: int, page: int, size: int, min_matches: int) -> SimilarResult:
    """The player's style features and nearest stylistic neighbours (KNN, written by refresh)."""
    rows = db.read(SIMILAR, {"id": player_id, "skip": (page - 1) * size, "limit": size})
    if not rows:
        raise NotFoundError(f"No player with id {player_id}")
    row = rows[0]
    if not row["hasStyle"]:
        if not db.read("MATCH (p:Player) WHERE p.styleVector IS NOT NULL RETURN p.id AS id LIMIT 1"):
            raise GdsUnavailableError(NOT_COMPUTED)
        raise NotFoundError(
            f"{row['player']['name']} has fewer than {min_matches} matches with serve statistics: no style vector"
        )
    return SimilarResult(
        player=row["player"],
        styleId=row["styleId"],
        features=row["features"],
        similar={"items": row["items"], "page": page, "size": size, "total": row["total"]},
    )


def traits(centre: dict[str, float]) -> list[StyleTrait]:
    """Up to MAX_TRAITS features where the centroid is furthest from average (|z| >= TRAIT_THRESHOLD)."""
    strongest = sorted(centre.items(), key=lambda item: abs(item[1]), reverse=True)
    return [
        StyleTrait(feature=name, zScore=round(z, 2), label=TRAIT_LABELS[name][0 if z > 0 else 1])
        for name, z in strongest[:MAX_TRAITS]
        if abs(z) >= TRAIT_THRESHOLD
    ]


def centroid(vectors: list[list[float]]) -> dict[str, float]:
    """Mean standardised vector of a style, keyed by feature name."""
    return {name: round(statistics.fmean(column), 4) for name, column in zip(gds.FEATURES, zip(*vectors))}


def style_groups(db: Neo4jClient, style_id: int | None = None) -> dict[int, list[dict]]:
    """Members per style id, most prestigious first; GdsUnavailableError when no style exists."""
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in db.read(STYLE_MEMBERS, {"styleId": style_id}):
        groups[row["styleId"]].append(row)
    if not groups and style_id is None:
        raise GdsUnavailableError(NOT_COMPUTED)
    return groups


def summarise(style_id: int, members: list[dict]) -> StyleSummary:
    """Style summary: size, readable traits from the centroid, three best-known members."""
    return StyleSummary(
        id=style_id,
        size=len(members),
        traits=traits(centroid([m["vector"] for m in members])),
        examples=[m["player"] for m in members[:3]],
    )


def styles(db: Neo4jClient, page: int, size: int) -> Page[StyleSummary]:
    """All style communities, largest first (ids are numbered by size)."""
    groups = style_groups(db)
    ordered = [summarise(sid, groups[sid]) for sid in sorted(groups)]
    skip = (page - 1) * size
    return Page[StyleSummary](items=ordered[skip : skip + size], page=page, size=size, total=len(ordered))


def style(db: Neo4jClient, style_id: int, page: int, size: int) -> StyleDetail:
    """One style: traits, centroid and paginated members."""
    members = style_groups(db, style_id).get(style_id)
    if not members:
        if not style_groups(db):
            raise GdsUnavailableError(NOT_COMPUTED)
        raise NotFoundError(f"No style with id {style_id}")
    summary = summarise(style_id, members)
    skip = (page - 1) * size
    page_members = [
        StyleMember(player=m["player"], prestigeRank=m["prestigeRank"], matches=m["matches"])
        for m in members[skip : skip + size]
    ]
    return StyleDetail(
        **summary.model_dump(),
        centroid=centroid([m["vector"] for m in members]),
        members=Page[StyleMember](items=page_members, page=page, size=size, total=len(members)),
    )
