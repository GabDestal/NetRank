"""Tests for scripts.analytics (make analytics)."""
# pylint: disable=missing-function-docstring

import json

from neo4j.exceptions import ClientError, ServiceUnavailable

from scripts import analytics, common
from tests.fakes import FakeDriver

LOUVAIN = {"communityCount": 317, "modularity": 0.566}
COMPLETE = {"techniques": 706, "with_degree": 706, "with_betweenness": 706, "with_community": 706}


def analytics_driver(check=None, fail_on=None):
    def responder(query, _parameters):
        if query == fail_on:
            raise ClientError("procedure failed")
        if query == analytics.LOUVAIN_WRITE:
            return [LOUVAIN]
        if query == analytics.CHECK_QUERY:
            return [check or COMPLETE]
        return []

    return FakeDriver(responder)


def install(monkeypatch, driver):
    monkeypatch.setattr(common, "get_driver", lambda: driver)
    monkeypatch.setattr(common, "close_driver", lambda: None)


def test_compute_runs_both_projections_and_drops_them():
    driver = analytics_driver()
    summary = analytics.compute(driver)
    assert summary == {"community_count": 317, "modularity": 0.566} | COMPLETE
    run = [query for query, _, _ in driver.queries]
    assert run == [analytics.RESET_QUERY,
                   analytics.COOCCURRENCE_PROJECTION, analytics.BETWEENNESS_WRITE, analytics.DROP_PROJECTION,
                   analytics.SIMILARITY_PROJECTION, analytics.SIMILARITY_MUTATE, analytics.LOUVAIN_WRITE,
                   analytics.DROP_PROJECTION,
                   analytics.COMMUNITY_SIZE_QUERY, analytics.IMPORT_META_QUERY, analytics.CHECK_QUERY]
    graphs = [params["graph"] for query, params, _ in driver.queries if params and "graph" in params]
    assert graphs[0] == graphs[1] == graphs[2] and graphs[3] == graphs[4] == graphs[5] == graphs[6]
    assert graphs[0] != graphs[3]


def test_compute_records_parameters_and_results():
    driver = analytics_driver()
    analytics.compute(driver)
    meta = next(params for query, params, _ in driver.queries if query == analytics.IMPORT_META_QUERY)
    assert json.loads(meta["parameters"]) == analytics.PARAMETERS
    assert meta["community_count"] == 317 and meta["modularity"] == 0.566
    louvain = next(params for query, params, _ in driver.queries if query == analytics.LOUVAIN_WRITE)
    assert louvain["concurrency"] == 1


def test_projection_is_dropped_when_an_algorithm_fails(monkeypatch):
    driver = analytics_driver(fail_on=analytics.BETWEENNESS_WRITE)
    install(monkeypatch, driver)
    assert analytics.main() == 1
    assert [q for q, _, _ in driver.queries][-1] == analytics.DROP_PROJECTION


def test_main_succeeds_when_every_technique_has_its_properties(monkeypatch):
    install(monkeypatch, analytics_driver())
    assert analytics.main() == 0


def test_main_fails_when_properties_are_missing(monkeypatch):
    install(monkeypatch, analytics_driver(check=COMPLETE | {"with_community": 700}))
    assert analytics.main() == 1


def test_main_fails_when_neo4j_is_down(monkeypatch):
    def responder(query, parameters):
        raise ServiceUnavailable("down")

    install(monkeypatch, FakeDriver(responder))
    assert analytics.main() == 1
