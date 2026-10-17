"""Tests for the PROFILE benchmark script, with a fake driver standing in for Neo4j."""
# pylint: disable=missing-function-docstring

import pytest

from scripts import benchmark
from tests.fakes import FakeDriver, FakeRecord

PLAN = {"operatorType": "ProduceResults@neo4j", "dbHits": 0,
        "children": [{"operatorType": "Filter@neo4j", "dbHits": 5,
                      "children": [{"operatorType": "NodeByLabelScan@neo4j", "dbHits": 10, "children": []}]}]}


class ProfileSummary:
    """Summary of a PROFILE run: the plan and its timings."""

    def __init__(self, plan, ms):
        self.profile = plan
        self.result_available_after = ms
        self.result_consumed_after = 1


class ProfileResult:
    """Iterable result with a consumable summary."""

    def __init__(self, rows, plan, ms):
        self._rows = [FakeRecord(row) for row in rows]
        self._summary = ProfileSummary(plan, ms)

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        return self._summary


class ProfileDriver(FakeDriver):
    """Answers PROFILE queries with answer(query) -> (rows, plan) and records the DDL it is sent."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.profiled = []
        self.ms = iter(range(100))

    def session(self, **_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, _params):
        self.profiled.append(query)
        rows, plan = self.answer(query)
        return ProfileResult(rows, plan, next(self.ms))


def test_plan_stats_sums_hits_and_lists_operators_leaves_first():
    assert benchmark.plan_stats(PLAN) == (15, ["NodeByLabelScan", "Filter", "ProduceResults"])


def test_profile_skips_warmups_and_takes_the_median():
    driver = ProfileDriver(lambda query: ([{"x": 1}], PLAN))
    stats = benchmark.profile(driver, "MATCH (n) RETURN 1 AS x", {}, runs=3)
    assert len(driver.profiled) == benchmark.WARMUP_RUNS + 3 and driver.profiled[0].startswith("PROFILE ")
    assert stats["ms"] == 4 and stats["db_hits"] == 15 and stats["rows"] == 1  # runs 2, 3, 4 (+1 ms each)


def test_index_case_drops_then_restores_the_schema():
    driver = ProfileDriver(lambda query: ([{"x": 1}], PLAN))
    result = benchmark.run_case(driver, benchmark.CVSS_RANGE, runs=1)
    sent = [query for query, _, _ in driver.queries]
    assert sent[0] == benchmark.CVSS_RANGE.drop and "cve_cvss_score" in " ".join(sent[1:])
    assert sent[-1].startswith("CALL db.awaitIndexes") and result["before"]["db_hits"] == 15


def test_index_case_restores_the_schema_even_on_failure():
    def answer(_query):
        if len(driver.profiled) > benchmark.WARMUP_RUNS + 1:
            raise RuntimeError("boom")
        return [], PLAN
    driver = ProfileDriver(answer)
    with pytest.raises(RuntimeError, match="boom"):
        benchmark.run_case(driver, benchmark.PRODUCT_LOOKUP, runs=1)
    assert driver.queries[-1][0].startswith("CALL db.awaitIndexes")


def test_rewrite_case_must_return_the_same_rows():
    case = benchmark.EXPOSURE_GROUPS
    same = benchmark.run_case(ProfileDriver(lambda query: ([{"g": 1}], PLAN)), case, runs=1)
    assert same["case"] == case.name
    different = ProfileDriver(lambda query: ([{"g": 1 if "UNWIND" in query else 2}], PLAN))
    with pytest.raises(RuntimeError, match="different rows"):
        benchmark.run_case(different, case, runs=1)


def test_main_prints_the_table(monkeypatch, capsys):
    monkeypatch.setattr(benchmark, "run_with_driver", lambda work, logger: work(
        ProfileDriver(lambda query: ([{"x": 1}], PLAN))))
    assert benchmark.main(["--runs", "1"]) == 0
    out = capsys.readouterr().out
    assert "| CVSS range (D8 index) | before | 15 | 1 |" in out and "NodeByLabelScan > Filter" in out


def test_main_fails_when_neo4j_is_unreachable(monkeypatch):
    monkeypatch.setattr(benchmark, "run_with_driver", lambda work, logger: None)
    assert benchmark.main([]) == 1
