"""Unit tests for eras, style features/traits, GDS helpers and the analytics endpoints (Neo4j faked)."""

from datetime import date

import pytest
from neo4j.exceptions import ClientError

from app.errors import GdsUnavailableError, InvalidRequestError, NotFoundError
from app.services import analytics, gds

FED = {"id": 103819, "name": "Roger Federer", "ioc": "SUI", "hand": "R", "dob": date(1981, 8, 8)}
FEATURES = dict.fromkeys(gds.FEATURES, 0.5)


# --------------------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2000s", ("2000-2009", 2000, 2009)),
        ("2004-2008", ("2004-2008", 2004, 2008)),
        ("2010", ("2010", 2010, 2010)),
        ("1980s", None),
        ("1985-1995", ("1991-1995", 1991, 1995)),
        ("2020s", ("2020-2026", 2020, 2026)),
    ],
)
def test_parse_era(text, expected):
    """Decades, ranges and single seasons, clipped to 1991-2026; a decade before the data is a 400."""
    if expected is None:
        with pytest.raises(InvalidRequestError):
            analytics.parse_era(text)
        return
    era = analytics.parse_era(text)
    assert (era.label, era.startYear, era.endYear) == expected


@pytest.mark.parametrize("text", [None, "", "all", " All-Time "])
def test_parse_era_all_time(text):
    """Missing or 'all' means all-time."""
    assert analytics.parse_era(text) is None


@pytest.mark.parametrize("text", ["nineties", "2010-2005", "20000"])
def test_parse_era_rejects_nonsense(text):
    """Unparseable or inverted ranges are a 400."""
    with pytest.raises(InvalidRequestError):
        analytics.parse_era(text)


def test_style_features_from_aggregates():
    """Percentages come from the right numerators and denominators; zero denominators give 0."""
    row = {
        "servePoints": 100,
        "aces": 10,
        "doubleFaults": 3,
        "firstIn": 60,
        "firstWon": 45,
        "secondWon": 20,
        "bpSaved": 6,
        "bpFaced": 10,
        "oppServePoints": 100,
        "oppServeWon": 62,
        "oppBpFaced": 8,
        "oppBpSaved": 5,
        "wins": 10,
        "clayWins": 5,
        "grassWins": 1,
        "hardWins": 4,
    }
    features = gds.style_features(row)
    assert features["acePct"] == 0.1 and features["firstServeWonPct"] == 0.75
    assert features["secondServeWonPct"] == 0.5 and features["returnPointsWonPct"] == 0.38
    assert features["breakPointsConvertedPct"] == 3 / 8 and features["clayWinShare"] == 0.5
    assert gds.style_features({**row, "wins": 0, "bpFaced": 0})["clayWinShare"] == 0.0


def test_standardise_centres_each_feature():
    """Each feature column has mean 0; a constant column stays 0 instead of dividing by zero."""
    low = dict.fromkeys(gds.FEATURES, 0.2) | {"acePct": 0.05}
    high = dict.fromkeys(gds.FEATURES, 0.2) | {"acePct": 0.15}
    vectors = gds.standardise([low, high])
    assert vectors[0][0] == -1.0 and vectors[1][0] == 1.0
    assert vectors[0][1] == 0.0


def test_traits_pick_the_strongest_deviations():
    """Up to three features with |z| >= 0.5, signed labels."""
    centre = dict.fromkeys(gds.FEATURES, 0.0) | {"acePct": 1.4, "returnPointsWonPct": -0.9, "clayWinShare": 0.4}
    traits = analytics.traits(centre)
    assert [(t.feature, t.label) for t in traits] == [("acePct", "big server"), ("returnPointsWonPct", "weak returner")]


def test_percentile():
    """Best of 4 is above 75% of players; empty ranking gives 0."""
    assert analytics.percentile(1, 4) == 0.75 and analytics.percentile(1, 0) == 0.0


# --------------------------------------------------------------------------- GDS helpers


class RecordingDb:
    """Answers queries from a list of callables/results in order and records them."""

    def __init__(self, answers):
        """`answers` are returned (or raised) one per call."""
        self.answers = list(answers)
        self.queries = []

    def write(self, query, params=None):
        """Record and answer."""
        self.queries.append((query, params))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    read = write


def test_era_ranking_is_cached_and_drops_its_projection():
    """First call projects, streams and drops; the second is served from the cache."""
    gds.clear_era_cache()
    db = RecordingDb([[{"nodeCount": 3, "relationshipCount": 2}], [{"id": 1, "score": 2.0}], [{"graphName": "g"}]])
    assert gds.era_ranking(db, 2001, 2002) == [{"id": 1, "score": 2.0}]
    assert gds.era_ranking(db, 2001, 2002) == [{"id": 1, "score": 2.0}]
    assert len(db.queries) == 3 and "gds.graph.drop" in db.queries[2][0]
    assert db.queries[0][1]["start"] == date(2001, 1, 1) and db.queries[0][1]["end"] == date(2003, 1, 1)
    gds.clear_era_cache()


def test_era_without_matches_is_404_and_still_drops():
    """An empty window raises NotFoundError and the (empty) projection is dropped."""
    gds.clear_era_cache()
    db = RecordingDb([[{"nodeCount": 0, "relationshipCount": 0}], [{"graphName": "g"}]])
    with pytest.raises(NotFoundError):
        gds.era_ranking(db, 1991, 1991)
    assert "gds.graph.drop" in db.queries[-1][0]


def test_gds_client_errors_become_503():
    """A failing GDS procedure is reported as GdsUnavailableError with the server code only."""
    db = RecordingDb([ClientError("There is no procedure with the name `gds.pageRank.stream`")])
    with pytest.raises(GdsUnavailableError, match="GDS call failed"):
        gds.gds_call(db, "CALL gds.pageRank.stream('g')")


def test_seeded_and_community_algorithms_are_single_threaded():
    """GDS only accepts randomSeed on KNN with concurrency 1; Louvain is pinned too so style ids are stable."""
    assert "randomSeed: $seed, concurrency: 1" in gds.KNN_MUTATE
    assert "concurrency: 1" in gds.LOUVAIN_WRITE
    assert "concurrency: $concurrency" in gds.PAGERANK_WRITE and "randomSeed: $seed" in gds.FASTRP_STREAM


def test_fastrp_with_no_matches_before_cutoff_is_empty():
    """Nothing before the cutoff: no embeddings, projection dropped."""
    db = RecordingDb([[{"nodeCount": 0}], [{"graphName": "g"}]])
    assert gds.fastrp_embeddings(db, date(1900, 1, 1)) == {}
    assert db.queries[0][1]["cutoff"] == date(1900, 1, 1)


# --------------------------------------------------------------------------- endpoints


def test_all_time_prestige_needs_a_refresh(api_client, fake_db_factory):
    """Player exists but prestige was never written: 503 telling what to run."""
    fake_db_factory({"COUNT { (q:Player)": [{"player": FED, "score": None, "rank": None, "ranked": 0}]})
    response = api_client.get("/api/players/103819/prestige")
    assert response.status_code == 503 and "gds/refresh" in response.json()["detail"]


def test_all_time_prestige(api_client, fake_db_factory):
    """Stored score and rank, with percentile."""
    fake_db_factory({"COUNT { (q:Player)": [{"player": FED, "score": 29.4, "rank": 2, "ranked": 2316}]})
    body = api_client.get("/api/players/103819/prestige").json()
    assert body["rank"] == 2 and body["era"] is None and body["percentile"] == round(2314 / 2316, 4)


def test_era_prestige_and_board(api_client, fake_db_factory, monkeypatch):
    """Era results come from the ranking; a player absent from the era is a 404 naming them."""
    ranking = [{"id": 1, "score": 3.0}, {"id": FED["id"], "score": 2.0}]
    monkeypatch.setattr(gds, "era_ranking", lambda db, start, end: ranking)
    fake_db_factory({"WHERE p.id IN $ids": lambda q, p: [{"player": {**FED, "id": i}} for i in p["ids"]]})
    body = api_client.get("/api/players/103819/prestige", params={"era": "2000s"}).json()
    assert (body["rank"], body["playersRanked"], body["era"]["label"]) == (2, 2, "2000-2009")
    board = api_client.get("/api/prestige", params={"era": "2004-2005", "size": 1, "page": 2}).json()
    assert board["ranking"]["total"] == 2 and board["ranking"]["items"][0]["rank"] == 2
    monkeypatch.setattr(gds, "era_ranking", lambda db, start, end: [{"id": 1, "score": 1.0}])
    missing = api_client.get("/api/players/103819/prestige", params={"era": "1995"})
    assert missing.status_code == 404 and "Roger Federer played no tour-level match in 1995" in missing.text


def test_similar_states(api_client, fake_db_factory):
    """Neighbours returned; no vector -> 404 if others have one, 503 if nobody does."""
    neighbour = {"player": {**FED, "id": 1}, "score": 0.97, "styleId": 5, "features": FEATURES}
    row = {"player": FED, "styleId": 5, "hasStyle": True, "features": FEATURES, "total": 1, "items": [neighbour]}
    fake_db_factory({"SIMILAR_STYLE": [row]})
    assert api_client.get("/api/players/103819/similar").json()["similar"]["items"][0]["score"] == 0.97
    no_style = {**row, "hasStyle": False, "styleId": None, "total": 0, "items": []}
    fake_db_factory({"SIMILAR_STYLE": [no_style], "LIMIT 1": [{"id": 1}]})
    assert "fewer than 50 matches" in api_client.get("/api/players/103819/similar").json()["detail"]
    fake_db_factory({"SIMILAR_STYLE": [no_style], "LIMIT 1": []})
    assert api_client.get("/api/players/103819/similar").status_code == 503


def test_styles_list_and_detail(api_client, fake_db_factory):
    """Styles are grouped, summarised with traits, and paginated; unknown id 404; none at all 503."""
    vector = [1.4] + [0.0] * (len(gds.FEATURES) - 1)
    members = [
        {"styleId": 1, "player": {**FED, "id": i}, "vector": vector, "prestigeRank": i, "matches": 60} for i in (1, 2)
    ]
    fake_db_factory({"p.styleId IS NOT NULL AND": lambda q, p: [m for m in members if p["styleId"] in (None, 1)]})
    listing = api_client.get("/api/styles").json()
    assert listing["total"] == 1 and listing["items"][0]["traits"][0]["label"] == "big server"
    detail = api_client.get("/api/styles/1", params={"size": 1}).json()
    assert detail["members"]["total"] == 2 and detail["centroid"]["acePct"] == 1.4
    assert api_client.get("/api/styles/2").status_code == 404
    fake_db_factory({"p.styleId IS NOT NULL AND": []})
    assert api_client.get("/api/styles").status_code == 503
