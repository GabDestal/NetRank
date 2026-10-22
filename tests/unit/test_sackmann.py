"""Unit tests for the Sackmann loader on a tiny synthetic file set."""

from datetime import date

import pandas as pd
import pytest

from scripts import sackmann

MATCH_COLUMNS = (
    "tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,match_num,"
    "winner_id,winner_seed,winner_entry,winner_name,winner_hand,winner_ht,winner_ioc,winner_age,"
    "loser_id,loser_seed,loser_entry,loser_name,loser_hand,loser_ht,loser_ioc,loser_age,"
    "score,best_of,round,minutes,"
    "w_ace,w_df,w_svpt,w_1stIn,w_1stWon,w_2ndWon,w_SvGms,w_bpSaved,w_bpFaced,"
    "l_ace,l_df,l_svpt,l_1stIn,l_1stWon,l_2ndWon,l_SvGms,l_bpSaved,l_bpFaced,"
    "winner_rank,winner_rank_points,loser_rank,loser_rank_points"
)
STATS = "10,2,80,50,40,15,12,3,4,5,4,70,40,28,12,11,2,6"


def row(edition, num, pair, score="6-4 6-4"):
    """One CSV line: match `num` of `edition` (id, level, date) between `pair` (winner, loser)."""
    tid, level, day = edition
    winner, loser = pair
    return (
        f"{tid},Event  {tid},Hard,32,{level},{day},{num},"
        f"{winner},1,,W,R,185,SUI,25.0,{loser},,Q,L,L,180,ESP,22.0,"
        f"{score},3,R32,90,{STATS},1,9000,50,700"
    )


PLAYERS_CSV = [
    "player_id,name_first,name_last,hand,dob,ioc,height,wikidata_id",
    "1,Roger,Federer,R,19810808,SUI,185,Q1426",
    "2,Rafael,Nadal,L,19860603,ESP,185,",
    "3,Martin,Landaluce,R,20060108,ESP,,",
    "4,Martin,Landaluce,R,20060108,ESP,,",
    "5,Joaquin ,Aguilar  Cardozo,R,,PAR,,",
]


@pytest.fixture(name="raw_dir")
def fixture_raw_dir(tmp_path):
    """A raw directory with one matches file and a players file containing a duplicate."""
    lines = [
        MATCH_COLUMNS,
        row(("1990-1", "A", 19901231), 1, (1, 2)),  # before 1991: dropped
        row(("1991-9", "D", 19910301), 1, (1, 2)),  # Davis Cup: dropped
        row(("1991-7", "G", 19910114), 1, (1, 2)),
        row(("1991-7", "G", 19910114), 2, (3, 1), score="W/O"),
        row(("1991-8", "A", 19910211), 1, (4, 1), score="6-3 2-1 RET"),
    ]
    (tmp_path / "atp_matches_1991.csv").write_text("\n".join(lines), encoding="utf-8")
    (tmp_path / "atp_players.csv").write_text("\n".join(PLAYERS_CSV) + "\n", encoding="utf-8")
    return tmp_path


def test_scope_keeps_tour_level_since_1991(raw_dir):
    """Pre-1991 and Davis Cup rows are filtered out."""
    matches = sackmann.read_matches(raw_dir)
    assert sorted(matches["tourney_id"].unique()) == ["1991-7", "1991-8"]


def test_duplicate_players_merge_into_the_busiest_id(raw_dir):
    """Same name and birth date -> one canonical id (the one with more matches)."""
    matches = sackmann.read_matches(raw_dir)
    players = sackmann.read_players(raw_dir)
    assert sackmann.canonical_ids(players, matches) in ({3: 4}, {4: 3})


def test_player_names_collapse_whitespace(raw_dir):
    """Double spaces in the source are normalised."""
    players = sackmann.read_players(raw_dir)
    assert "Joaquin Aguilar Cardozo" in set(players["name"])


def test_player_records_convert_types(raw_dir):
    """Birth dates become dates, missing values become None."""
    players = sackmann.read_players(raw_dir)
    nadal = next(p for p in sackmann.player_records(players, [2]) if p["id"] == 2)
    assert nadal["dob"] == date(1986, 6, 3)
    assert nadal["wikidataId"] is None


def test_match_records_flags_and_sides(raw_dir):
    """Walkovers and retirements are flagged; side stats land under readable names."""
    matches = sackmann.read_matches(raw_dir)
    records = {r["id"]: r for r in sackmann.match_records(matches, {3: 4})}
    assert records["1991-7-2"]["walkover"] and not records["1991-7-2"]["retired"]
    assert records["1991-8-1"]["retired"] and not records["1991-8-1"]["walkover"]
    assert records["1991-7-2"]["winnerId"] == 4  # remapped duplicate
    first = records["1991-7-1"]
    assert first["winner"]["aces"] == 10 and first["loser"]["entry"] == "Q"
    assert first["winner"]["rank"] == 1 and first["date"] == date(1991, 1, 14)


def test_tournament_records_one_per_edition(raw_dir):
    """Each tourney_id becomes one Tournament with level metadata."""
    tournaments = sackmann.tournament_records(sackmann.read_matches(raw_dir))
    assert {t["id"]: t["levelName"] for t in tournaments} == {"1991-7": "Grand Slam", "1991-8": "ATP Tour"}
    assert tournaments[0]["name"] == "Event 1991-7"


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA])
def test_clean_maps_missing_to_none(value):
    """All pandas flavours of 'missing' become None."""
    assert sackmann.clean(value) is None


def test_to_date_rejects_impossible_dates():
    """A malformed YYYYMMDD gives None instead of raising."""
    assert sackmann.to_date(19811399) is None
