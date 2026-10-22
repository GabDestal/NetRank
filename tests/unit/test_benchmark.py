"""Unit tests for the benchmark helpers (plan parsing, comparison, rendering)."""

import pytest

from scripts import benchmark

PLAN = {
    "operatorType": "ProduceResults@neo4j",
    "dbHits": 0,
    "rows": 1,
    "children": [
        {"operatorType": "Top@neo4j", "dbHits": 5, "children": [
            {"operatorType": "NodeUniqueIndexSeek@neo4j", "dbHits": 2, "children": []},
        ]},
    ],
}


class FakeDb:
    """Returns fixed rows and plan; counts reads."""

    def __init__(self, rows_by_query):
        """`rows_by_query` maps a query to the rows it returns."""
        self.rows_by_query = rows_by_query
        self.reads = 0

    def profile(self, query, _params):
        """Rows for the query and the shared fake plan."""
        return self.rows_by_query[query], PLAN

    def read(self, query, _params):
        """Rows for the query."""
        self.reads += 1
        return self.rows_by_query[query]


CASE = benchmark.Case("Demo", "index", {"id": 1}, "BEFORE", "AFTER", note="a caveat")


def test_plan_stats_sums_hits_and_keeps_key_operators():
    """db hits are summed over the tree; the planner suffix is stripped; only key operators are kept."""
    assert benchmark.plan_stats(PLAN) == {"dbHits": 7, "rows": 1, "operators": ["NodeUniqueIndexSeek", "Top"]}


def test_measure_times_both_sides_and_checks_results():
    """Both sides are profiled and timed (warm-up + runs); differing results raise."""
    db = FakeDb({"BEFORE": [{"n": 1}], "AFTER": [{"n": 1}]})
    sides = benchmark.measure(db, CASE)
    assert sides["after"]["dbHits"] == 7 and sides["before"]["result"] == [{"n": 1}]
    assert db.reads == 2 * (benchmark.WARMUP + benchmark.RUNS)
    with pytest.raises(AssertionError, match="disagree"):
        benchmark.measure(FakeDb({"BEFORE": [{"n": 1}], "AFTER": [{"n": 2}]}), CASE)


def test_ratio_and_render():
    """The table shows the gain; notes are flagged in the table and printed under the plans."""
    assert benchmark.ratio(1000, 10) == "100x" and benchmark.ratio(5, 0) == "n/a"
    side = {"dbHits": 1000, "ms": 12.0, "operators": ["NodeByLabelScan"], "result": []}
    results = [(CASE, {"before": side, "after": {**side, "dbHits": 10, "ms": 1.0}})]
    text = benchmark.render(results, {"version": "5", "edition": "x"})
    assert "| Demo (see note) | index | 1,000 | 10 | 100x | 12.0 | 1.0 |" in text
    assert "- Note: a caveat" in text and "## Investigated without gain" in text


def test_every_case_is_parameterised():
    """No benchmark query builds values into the string: each one uses $parameters."""
    for case in benchmark.CASES:
        assert "$" in case.before and "$" in case.after, case.name
