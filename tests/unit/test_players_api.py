"""API tests for the player and graph endpoints, with Neo4j faked."""

from datetime import date

import pytest
from neo4j.exceptions import ServiceUnavailable

from app.services.players import lucene_query

FED = {"id": 103819, "name": "Roger Federer", "ioc": "SUI", "hand": "R", "dob": date(1981, 8, 8)}
NADAL = {"id": 104745, "name": "Rafael Nadal", "ioc": "ESP", "hand": "L", "dob": date(1986, 6, 3)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Feder", "feder*"),
        ("rog  FED", "rog* AND fed*"),
        ("Núñez", "nunez*"),
        ('fed" OR *:*', "fed* AND or*"),
        ("--", ""),
    ],
)
def test_lucene_query_is_prefix_only_and_safe(text, expected):
    """Words become folded prefixes; Lucene syntax in the input is dropped."""
    assert lucene_query(text) == expected


def test_search_passes_paging_and_returns_page(api_client, fake_db_factory):
    """page/size become skip/limit; the response is a Page."""
    fake = fake_db_factory({"queryNodes": [{"total": 31, "items": [{**FED, "score": 2.5}]}]})
    body = api_client.get("/api/players", params={"q": "fed", "page": 3, "size": 10}).json()
    assert body["total"] == 31 and body["page"] == 3 and body["items"][0]["name"] == "Roger Federer"
    assert fake.calls[0][1] == {"query": "fed*", "skip": 20, "limit": 10}


def test_search_without_usable_words_skips_the_database(api_client, fake_db_factory):
    """Punctuation-only input returns an empty page without querying."""
    fake = fake_db_factory({})
    assert api_client.get("/api/players", params={"q": "--"}).json()["total"] == 0
    assert not fake.calls


@pytest.mark.parametrize("params", [{"q": "a"}, {"q": "fed", "size": 101}, {"q": "fed", "page": 0}])
def test_search_validates_parameters(api_client, fake_db_factory, params):
    """Too-short queries and out-of-range paging are rejected with 422."""
    fake_db_factory({})
    assert api_client.get("/api/players", params=params).status_code == 422


def test_profile_computes_win_rates(api_client, fake_db_factory):
    """Per-surface win rate is computed from wins and losses."""
    row = {
        "player": {**FED, "height": 185, "wikidataId": "Q1426"},
        "matches": 10, "wins": 7, "losses": 3, "titles": 1, "bestRank": 1,
        "firstMatch": date(1998, 7, 6), "lastMatch": date(2021, 6, 28),
        "bySurface": [{"surface": "Grass", "wins": 3, "losses": 1}],
    }
    fake_db_factory({"AS bestRank": [row]})
    body = api_client.get("/api/players/103819").json()
    assert body["bySurface"] == [{"surface": "Grass", "wins": 3, "losses": 1, "winRate": 0.75}]
    assert body["titles"] == 1 and body["height"] == 185


def test_unknown_player_is_404(api_client, fake_db_factory):
    """No row from the profile query means 404 with a message."""
    fake_db_factory({"AS bestRank": []})
    response = api_client.get("/api/players/1")
    assert response.status_code == 404 and response.json() == {"detail": "No player with id 1"}


def test_matches_filters_reach_the_query(api_client, fake_db_factory):
    """Surface and dates are passed as parameters, never interpolated."""
    fake = fake_db_factory({"rows[$skip": [{"total": 0, "items": []}]})
    api_client.get("/api/players/103819/matches", params={"surface": "Clay", "since": "2010-01-01", "size": 5})
    params = fake.calls[0][1]
    assert params["surface"] == "Clay" and params["since"] == date(2010, 1, 1) and params["until"] is None
    assert params["limit"] == 5


def test_matches_of_unknown_player_is_404(api_client, fake_db_factory):
    """No rows and no player: 404; no rows but the player exists: empty page."""
    fake_db_factory({"rows[$skip": [], "RETURN p.id AS id": []})
    assert api_client.get("/api/players/1/matches").status_code == 404
    fake_db_factory({"rows[$skip": [], "RETURN p.id AS id": [{"id": 1}]})
    assert api_client.get("/api/players/1/matches").json()["total"] == 0


def test_matches_rejects_inverted_dates_and_unknown_surface(api_client, fake_db_factory):
    """since > until is a 400; an unknown surface is a 422."""
    fake_db_factory({})
    url = "/api/players/1/matches"
    assert api_client.get(url, params={"since": "2020-01-01", "until": "2019-01-01"}).status_code == 400
    assert api_client.get(url, params={"surface": "Sand"}).status_code == 422


def test_head_to_head_counts_played_matches_only(api_client, fake_db_factory):
    """Walkovers are listed but not counted in the records."""
    meeting = {"date": date(2019, 7, 12), "tournament": "Wimbledon", "round": "SF", "score": "7-6 1-6 6-3 6-4"}
    matches = [
        {**meeting, "matchId": "m1", "surface": "Grass", "winnerId": FED["id"], "walkover": False},
        {**meeting, "matchId": "m2", "surface": "Clay", "winnerId": NADAL["id"], "walkover": False},
        {**meeting, "matchId": "m3", "surface": "Hard", "winnerId": NADAL["id"], "walkover": True, "score": "W/O"},
    ]
    fake_db_factory({"AS player1": [{"player1": FED, "player2": NADAL, "matches": matches}]})
    body = api_client.get("/api/h2h", params={"p1": FED["id"], "p2": NADAL["id"]}).json()
    assert (body["player1Wins"], body["player2Wins"]) == (1, 1)
    assert body["bySurface"] == [
        {"surface": "Clay", "player1Wins": 0, "player2Wins": 1},
        {"surface": "Grass", "player1Wins": 1, "player2Wins": 0},
    ]
    assert len(body["matches"]) == 3


def test_head_to_head_errors(api_client, fake_db_factory):
    """Same player twice is 400; an unknown id is 404."""
    fake_db_factory({"AS player1": []})
    assert api_client.get("/api/h2h", params={"p1": 5, "p2": 5}).status_code == 400
    assert api_client.get("/api/h2h", params={"p1": 5, "p2": 6}).status_code == 404


def test_nemesis_combines_nemeses_and_triangles(api_client, fake_db_factory):
    """Nemeses are paginated; triangles carry their head-to-head record."""
    nemesis_row = {
        "player": FED,
        "total": 1,
        "items": [
            {"opponent": NADAL, "winsOverPlayer": 24, "lossesToPlayer": 16, "lastWinOverPlayer": date(2019, 5, 27)}
        ],
    }
    triangle = {"second": NADAL, "third": FED, "record": ["2-1", "3-0", "1-0"], "weakestLead": 1}
    fake = fake_db_factory({"AS nemeses": [nemesis_row], "weakestLead": [{"total": 7, "items": [triangle]}]})
    body = api_client.get("/api/players/103819/nemesis", params={"min_wins": 3, "triangles": 1}).json()
    assert body["nemeses"]["total"] == 1 and body["triangleCount"] == 7
    assert body["triangles"][0]["record"] == ["2-1", "3-0", "1-0"]
    assert fake.calls[0][1]["minWins"] == 3 and fake.calls[1][1]["limit"] == 1


def test_beat_chain_success_and_failures(api_client, fake_db_factory):
    """A found chain is returned; no chain is 404; same player is 400; hop bounds are validated."""
    hop = {
        "winner": FED, "loser": NADAL, "wins": 16, "matchId": "m1", "date": date(2019, 7, 12),
        "tournament": "Wimbledon", "round": "SF", "score": "7-6 1-6 6-3 6-4",
    }
    found = {"source": FED, "target": NADAL, "found": True, "chain": [hop]}
    fake = fake_db_factory({"SHORTEST 1": [found]})
    body = api_client.get("/api/path", params={"from": FED["id"], "to": NADAL["id"], "max_hops": 3}).json()
    assert body["hops"] == 1 and fake.calls[0][1] == {"source": FED["id"], "target": NADAL["id"], "maxHops": 3}
    fake_db_factory({"SHORTEST 1": [{**found, "found": False, "chain": []}]})
    assert api_client.get("/api/path", params={"from": 1, "to": 2}).status_code == 404
    fake_db_factory({"SHORTEST 1": []})
    assert api_client.get("/api/path", params={"from": 1, "to": 2}).json()["detail"] == "No player with id 1 or 2"
    assert api_client.get("/api/path", params={"from": 1, "to": 1}).status_code == 400
    assert api_client.get("/api/path", params={"from": 1, "to": 2, "max_hops": 7}).status_code == 422


def test_database_outage_is_503_on_any_endpoint(api_client, fake_db_factory):
    """The app-level handler turns a driver outage into 503 without leaking the driver message."""
    fake_db_factory({"AS bestRank": ServiceUnavailable("routing table: secret details")})
    response = api_client.get("/api/players/1")
    assert response.status_code == 503 and "secret" not in response.text
