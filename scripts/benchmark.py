"""Before/after query benchmarks with PROFILE, written to docs/benchmarks.md.

Each case runs a "before" query (what a first draft or a generic schema would do) and the
"after" query the API uses. Both must return the same result; the report shows database hits,
rows, the operators that changed and the median latency over several runs.

`USING SCAN` hints force a label scan for the "before" side of index cases, so the index does not
need to be dropped. Usage: python -m scripts.benchmark (needs the loaded graph).
"""

import logging
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.database.client import Neo4jClient
from app.services.health import SERVER_INFO

DOC = Path("docs/benchmarks.md")
RUNS = 7
WARMUP = 2
FEDERER, DJOKOVIC, KRIEK = 103819, 104925, 100532
KEY_OPERATORS = (
    "NodeByLabelScan",
    "NodeIndexSeek",
    "NodeUniqueIndexSeek",
    "NodeIndexSeekByRange",
    "NodeByIdSeek",
    "CartesianProduct",
    "Expand(All)",
    "Expand(Into)",
    "OptionalExpand(All)",
    "StatefulShortestPath(All)",
    "StatefulShortestPath(Into)",
    "ProcedureCall",
    "Eager",
    "Sort",
    "Top",
    "EagerAggregation",
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Case:
    """One before/after pair; both queries must return identical rows."""

    name: str
    change: str
    params: dict
    before: str
    after: str
    note: str = ""


CASES = [
    Case(
        "Exact name lookup",
        "Range index on Player.name instead of scanning every Player",
        {"name": "Roger Federer"},
        "MATCH (p:Player) USING SCAN p:Player WHERE p.name = $name RETURN p.id AS id",
        "MATCH (p:Player) WHERE p.name = $name RETURN p.id AS id",
    ),
    Case(
        "Name search (substring)",
        "Full-text index with accent folding instead of toLower/CONTAINS on every Player",
        {"text": "federer", "query": "federer*"},
        "MATCH (p:Player) WHERE toLower(p.name) CONTAINS $text RETURN p.id AS id ORDER BY id",
        "CALL db.index.fulltext.queryNodes('player_name_ft', $query) YIELD node " + "RETURN node.id AS id ORDER BY id",
        "db hits do not count the work done inside the full-text procedure (Lucene). With 2,316 players a"
        + " scan is cheap, and latency is about equal; the index is chosen for accent folding and"
        + " word-prefix matching, and because a scan grows with the number of players.",
    ),
    Case(
        "Matches in one week",
        "Range index on Match.date instead of scanning all 102k matches",
        {"since": "2019-07-01", "until": "2019-07-14"},
        "MATCH (m:Match) USING SCAN m:Match WHERE m.date >= date($since) AND m.date <= date($until) "
        + "RETURN count(m) AS n",
        "MATCH (m:Match) WHERE m.date >= date($since) AND m.date <= date($until) RETURN count(m) AS n",
    ),
    Case(
        "Career totals",
        "Conditional counts in one subquery instead of chained OPTIONAL MATCH (rows multiply: wins x losses)",
        {"id": FEDERER},
        "MATCH (p:Player {id: $id}) OPTIONAL MATCH (p)-[:WON]->(w:Match) WHERE NOT w.walkover "
        + "OPTIONAL MATCH (p)-[:LOST]->(l:Match) WHERE NOT l.walkover "
        + "RETURN count(DISTINCT w) AS wins, count(DISTINCT l) AS losses",
        "MATCH (p:Player {id: $id}) CALL (p) { MATCH (p)-[r:WON|LOST]->(m:Match) WHERE NOT m.walkover "
        + "RETURN count(CASE WHEN type(r) = 'WON' THEN 1 END) AS wins, "
        + "count(CASE WHEN type(r) = 'LOST' THEN 1 END) AS losses } RETURN wins, losses",
    ),
    Case(
        "Nemesis top 10",
        "Read the derived BEAT edge instead of aggregating matches",
        {"id": FEDERER},
        "MATCH (p:Player {id: $id})-[:LOST]->(m:Match)<-[:WON]-(o:Player) WHERE NOT m.walkover "
        + "WITH o, count(m) AS wins ORDER BY wins DESC, o.name LIMIT 10 RETURN o.id AS id, wins",
        "MATCH (p:Player {id: $id})<-[b:BEAT]-(o:Player) WITH o, b.wins AS wins "
        + "ORDER BY wins DESC, o.name LIMIT 10 RETURN o.id AS id, wins",
    ),
    Case(
        "Beat cycles through a player",
        "3-cycle over BEAT instead of over Match nodes (6 hops, no aggregation before the join)",
        {"id": DJOKOVIC},
        "MATCH (a:Player {id: $id})-[:WON]->(m1:Match)<-[:LOST]-(b:Player) WHERE NOT m1.walkover "
        + "WITH DISTINCT a, b MATCH (b)-[:WON]->(m2:Match)<-[:LOST]-(c:Player) WHERE NOT m2.walkover AND c <> a "
        + "WITH DISTINCT a, b, c WHERE EXISTS { (c)-[:WON]->(m3:Match)<-[:LOST]-(a) WHERE NOT m3.walkover } "
        + "RETURN count(*) AS cycles",
        "MATCH (a:Player {id: $id})-[:BEAT]->(b:Player)-[:BEAT]->(c:Player)-[:BEAT]->(a) "
        + "WHERE b <> c RETURN count(*) AS cycles",
    ),
    Case(
        "Beat chain (3 hops)",
        "SHORTEST over BEAT instead of a quantified path over Player-Match-Player",
        {"source": FEDERER, "target": KRIEK},
        "MATCH (s:Player {id: $source}) MATCH (t:Player {id: $target}) "
        + "MATCH p = SHORTEST 1 (s) ((x:Player)-[:WON]->(m:Match)<-[:LOST]-(y:Player) WHERE NOT m.walkover){1,6} (t) "
        + "RETURN length(p) / 2 AS hops",
        "MATCH (s:Player {id: $source}) MATCH (t:Player {id: $target}) "
        + "MATCH p = SHORTEST 1 (s)-[:BEAT]->{1,6}(t) RETURN length(p) AS hops",
    ),
]


# Measured by hand (2026-10-22, same setup) and kept out of CASES because nothing improved.
NO_GAIN = [
    "- **Match history page (Federer, 20 per page).** Cutting the page before the tournament, opponent and"
    + " odds lookups did not reduce work: the planner already avoids it. Same-field 'lookups then"
    + " ORDER BY/SKIP/LIMIT': 6,542 db hits, 14.5 ms; page first: 6,542 db hits, 9.4 ms, plus a separate"
    + " count query (3,000 db hits, 4.5 ms) for the total. The API keeps one query that returns page and"
    + " total together (8,237 db hits, 15.0 ms): one round trip, same latency.",
]


def flatten(plan: dict) -> list[dict]:
    """Every operator of a profiled plan tree, parent first."""
    return [plan] + [op for child in plan.get("children", []) for op in flatten(child)]


def plan_stats(plan: dict) -> dict:
    """Total db hits, rows produced by the root, and the key operators present."""
    operators = flatten(plan)
    names = {op["operatorType"].split("@")[0] for op in operators}
    return {
        "dbHits": sum(op.get("dbHits", 0) for op in operators),
        "rows": plan.get("rows", 0),
        "operators": sorted(name for name in names if name in KEY_OPERATORS),
    }


def median_ms(db: Neo4jClient, query: str, params: dict) -> float:
    """Median wall time over RUNS executions, after WARMUP unmeasured ones."""
    for _ in range(WARMUP):
        db.read(query, params)
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        db.read(query, params)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def measure(db: Neo4jClient, case: Case) -> dict:
    """Profile and time both sides of a case; fail loudly if their results differ."""
    sides = {}
    for side in ("before", "after"):
        query = getattr(case, side)
        rows, plan = db.profile(query, case.params)
        sides[side] = {**plan_stats(plan), "ms": median_ms(db, query, case.params), "result": rows}
    if sides["before"]["result"] != sides["after"]["result"]:
        raise AssertionError(f"{case.name}: before and after disagree")
    return sides


def ratio(before: float, after: float) -> str:
    """'123x' style improvement factor."""
    return f"{before / after:,.0f}x" if after else "n/a"


def render(results: list[tuple[Case, dict]], server: dict) -> str:
    """Markdown report."""
    lines = [
        "# Query benchmarks (PROFILE before / after)",
        "",
        f"Generated by `make benchmark` (`scripts/benchmark.py`) on Neo4j {server['version']} {server['edition']}, "
        + f"local Docker. Latency is the median of {RUNS} runs after {WARMUP} warm-ups, measured from the client. "
        + "Every pair is checked to return the same result.",
        "",
        "| Case | Change | db hits before | db hits after | gain | ms before | ms after |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case, sides in results:
        b, a = sides["before"], sides["after"]
        lines.append(
            f"| {case.name}{' (see note)' if case.note else ''} | {case.change} | {b['dbHits']:,} | {a['dbHits']:,} "
            + f"| {ratio(b['dbHits'], a['dbHits'])} "
            + f"| {b['ms']:,.1f} | {a['ms']:,.1f} |"
        )
    lines += ["", "## Investigated without gain", "", *NO_GAIN, "", "## Plans", ""]
    for case, sides in results:
        lines += [
            f"### {case.name}",
            "",
            f"- Before: {', '.join(sides['before']['operators']) or '-'}",
            f"- After: {', '.join(sides['after']['operators']) or '-'}",
            *([f"- Note: {case.note}"] if case.note else []),
            "",
            "```cypher",
            "// before",
            case.before.strip(),
            "// after",
            case.after.strip(),
            "```",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Neo4jClient.from_settings(get_settings())
    try:
        server = db.read(SERVER_INFO)[0]
        results = []
        for case in CASES:
            sides = measure(db, case)
            log.info(f"{case.name}: {sides['before']['dbHits']:,} -> {sides['after']['dbHits']:,} db hits")
            results.append((case, sides))
        DOC.write_text(render(results, server), encoding="utf-8", newline="\n")
        log.info(f"report written to {DOC}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
