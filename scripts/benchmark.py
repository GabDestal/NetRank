"""PROFILE benchmarks: each query measured with and without the index or rewrite that makes it fast.

For an index case, the "without" run drops the index, profiles the same query, and then recreates
everything with apply_schema in a finally block. If the script is killed in between, `make schema`
restores the index. Run it on your local database only, never on a shared one.
For a rewrite case, the slow and the fast query are both profiled and must return the same rows.

Usage:
    python -m scripts.benchmark [--runs 5]
"""

import argparse
import logging
import statistics
from dataclasses import dataclass
from typing import Any

from neo4j import Driver

from app.database.schema import apply_schema
from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("benchmark")
DEFAULT_RUNS = 5
WARMUP_RUNS = 2


@dataclass(frozen=True)
class Case:
    """One benchmark: a query, and either the index to drop or a slower query to compare it with."""

    name: str
    query: str
    params: dict[str, Any]
    drop: str = ""  # DDL removing the index the query relies on (index case)
    slow_query: str = ""  # an equivalent query written the naive way (rewrite case)


# D8's range index: CVEs above a severity, most severe first.
CVSS_RANGE = Case(
    name="CVSS range (D8 index)",
    query="MATCH (c:CVE) WHERE c.cvss_score >= $min_score "
          "RETURN c.cve_id AS cve_id, c.cvss_score AS score ORDER BY score DESC, cve_id LIMIT 20",
    params={"min_score": 9.8},
    drop="DROP INDEX cve_cvss_score IF EXISTS",
)

# The entry point of question 7: one product by key, through its uniqueness constraint's index.
PRODUCT_LOOKUP = Case(
    name="Product lookup (uniqueness constraint)",
    query="MATCH (p:Product {product_key: $product_key}) RETURN p.product_key AS product_key, p.name AS name",
    params={"product_key": "fortinet:fortios"},
    drop="DROP CONSTRAINT product_product_key IF EXISTS",
)

# Question 7's group ranking, product -> CVE -> technique <- group. The naive version expands every
# group once per (CVE, technique) path; the rewrite (used in EXPOSURE_QUERY) first reduces the CVEs to
# their distinct techniques and expands each technique's groups once.
EXPOSURE_GROUPS = Case(
    name="Exposure groups, 3 hops (rewrite)",
    slow_query="""
MATCH (:Product {product_key: $product_key})<-[:AFFECTS]-(:CVE)
      -[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)<-[:USES]-(g:Group)
WITH g, count(DISTINCT t) AS shared
ORDER BY shared DESC, g.name LIMIT 10
RETURN g.attack_id AS group_id, shared
""",
    query="""
MATCH (p:Product {product_key: $product_key})
UNWIND COLLECT { MATCH (p)<-[:AFFECTS]-(:CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
                 RETURN DISTINCT t } AS t
MATCH (t)<-[:USES]-(g:Group)
WITH g, count(t) AS shared
ORDER BY shared DESC, g.name LIMIT 10
RETURN g.attack_id AS group_id, shared
""",
    params={"product_key": "cisco:ios"},
)

CASES = (CVSS_RANGE, PRODUCT_LOOKUP, EXPOSURE_GROUPS)


def plan_stats(plan: dict[str, Any]) -> tuple[int, list[str]]:
    """Return the total db hits of a PROFILE plan tree and its operators, leaves first."""
    hits, operators = 0, []
    for child in plan.get("children", []):
        child_hits, child_ops = plan_stats(child)
        hits += child_hits
        operators += child_ops
    operators.append(plan["operatorType"].split("@")[0])
    return hits + plan.get("dbHits", 0), operators


def profile(driver: Driver, query: str, params: dict[str, Any], runs: int) -> dict[str, Any]:
    """PROFILE query runs times after a warm-up and return db hits, rows, median time (ms), plan and rows."""
    times, summary, rows = [], None, []
    with driver.session() as session:
        for i in range(WARMUP_RUNS + runs):
            result = session.run("PROFILE " + query, params)
            rows = [record.data() for record in result]
            summary = result.consume()
            if i >= WARMUP_RUNS:
                times.append(summary.result_available_after + summary.result_consumed_after)
    hits, operators = plan_stats(summary.profile)
    return {"db_hits": hits, "rows": len(rows), "ms": statistics.median(times),
            "plan": " > ".join(operators), "result": rows}


def run_case(driver: Driver, case: Case, runs: int) -> dict[str, Any]:
    """Measure one case and return its before (slow) and after (fast) PROFILE results."""
    after = profile(driver, case.query, case.params, runs)
    if case.slow_query:
        before = profile(driver, case.slow_query, case.params, runs)
    else:
        try:
            driver.execute_query(case.drop)
            before = profile(driver, case.query, case.params, runs)
        finally:
            apply_schema(driver)
            driver.execute_query("CALL db.awaitIndexes(300)")
    if before["result"] != after["result"]:
        raise RuntimeError(f"{case.name}: the two versions return different rows")
    return {"case": case.name, "before": before, "after": after}


def to_markdown(results: list[dict[str, Any]]) -> str:
    """Format the results as a Markdown table plus the plans."""
    lines = ["| Query | Version | db hits | rows | median ms |", "|---|---|---:|---:|---:|"]
    for res in results:
        for side in ("before", "after"):
            stats = res[side]
            lines.append(f"| {res['case']} | {side} | {stats['db_hits']:,} | {stats['rows']} | {stats['ms']:.0f} |")
    lines.append("")
    for res in results:
        lines.append(f"{res['case']}")
        lines.append(f"  before: {res['before']['plan']}")
        lines.append(f"  after:  {res['after']['plan']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run every benchmark and print the table. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="measured runs per query (after 2 warm-ups)")
    args = parser.parse_args(argv)
    setup_logging()
    results = run_with_driver(lambda driver: [run_case(driver, case, args.runs) for case in CASES], LOGGER)
    if results is None:
        return 1
    print(to_markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
