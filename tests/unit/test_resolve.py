"""Unit tests for entity resolution on small synthetic frames."""

import pandas as pd

from scripts import resolve
from scripts.names import tennisdata_key

MONDAY = pd.Timestamp("2015-06-01")


def sack_row(match_id, keys, **overrides):
    """One Sackmann match shaped like resolve.sackmann_keys output; `overrides` replace columns."""
    row = {
        "matchId": match_id,
        "tourneyDate": MONDAY,
        "tourneyName": "Paris",
        "sackRound": "R32",
        "winnerId": 1,
        "loserId": 2,
        "winnerRank": 10,
        "loserRank": 20,
        "winnerKey": keys[0],
        "loserKey": keys[1],
    }
    return {**row, **overrides}


def odds_row(row_id, names, day=3, **overrides):
    """One tennis-data row on MONDAY + `day`; `overrides` replace columns."""
    row = {
        "oddsRowId": row_id,
        "Date": MONDAY + pd.Timedelta(days=day),
        "Tournament": "French Open",
        "Location": "Paris",
        "Series": "Grand Slam",
        "Round": "1st Round",
        "Winner": names[0],
        "Loser": names[1],
        "WRank": 10,
        "LRank": 20,
        "winnerKey": tennisdata_key(names[0]),
        "loserKey": tennisdata_key(names[1]),
    }
    return {**row, **overrides}


FEDERER_NADAL = ("federer r", "nadal r")


def run(odds_rows, sack_rows):
    """Resolve and return (links indexed by oddsRowId, status by oddsRowId)."""
    links, odds = resolve.resolve(pd.DataFrame(odds_rows), pd.DataFrame(sack_rows))
    return links.set_index("oddsRowId"), odds.set_index("oddsRowId")["status"]


def test_exact_names_inside_the_window_link():
    """Same names on day 14 of a Slam (start Monday + 14) still link."""
    links, status = run([odds_row("o1", ("Federer R.", "Nadal R."), day=14)], [sack_row("m1", FEDERER_NADAL)])
    assert status["o1"] == "matched"
    assert links.loc["o1", "matchId"] == "m1" and links.loc["o1", "method"] == "exact"


def test_window_edges_are_respected():
    """Day -1 (Sunday start) and day 17 stay unmatched under the [0, 16] rule; diagnose counts day -1."""
    sack = [sack_row("m1", FEDERER_NADAL)]
    odds = [odds_row("early", ("Federer R.", "Nadal R."), day=-1), odds_row("late", ("Federer R.", "Nadal R."), day=17)]
    _, status = run(odds, sack)
    assert status["early"] == "unmatched" and status["late"] == "unmatched"
    _, frame = resolve.resolve(pd.DataFrame(odds), pd.DataFrame(sack))
    assert resolve.diagnose(frame, pd.DataFrame(sack))["exact_names_window_minus2"] == 1


def test_rows_after_the_cutoff_are_out_of_coverage():
    """Odds after Sackmann's last date are not counted as failures."""
    row = odds_row("o1", ("Federer R.", "Nadal R."))
    row["Date"] = resolve.SACKMANN_CUTOFF + pd.Timedelta(days=1)
    _, status = run([row], [sack_row("m1", FEDERER_NADAL)])
    assert status["o1"] == "out_of_coverage"


def test_compound_surname_links_through_variants():
    """'Ramos-Vinolas A.' matches Sackmann's 'Albert Ramos'."""
    links, _ = run([odds_row("o1", ("Ramos-Vinolas A.", "Nadal R."))], [sack_row("m1", ("ramos a", "nadal r"))])
    assert links.loc["o1", "method"] == "surname_variant"


def test_surname_only_needs_rank_agreement():
    """Different initial: linked when ranks agree, refused when they do not (brothers)."""
    sack = [sack_row("m1", ("dolgopolov a", "nadal r"), winnerRank=30, loserRank=2)]
    links, _ = run([odds_row("o1", ("Dolgopolov O.", "Nadal R."), WRank=31, LRank=2)], sack)
    assert links.loc["o1", "method"] == "surname_only"
    _, status = run([odds_row("o1", ("Dolgopolov O.", "Nadal R."), WRank=279, LRank=2)], sack)
    assert status["o1"] == "unmatched"


def test_round_breaks_a_rematch_inside_one_event():
    """Round robin then final between the same two players link to the right Sackmann rows."""
    sack = [
        sack_row("rr", FEDERER_NADAL, sackRound="RR"),
        sack_row("final", FEDERER_NADAL, sackRound="F"),
    ]
    odds = [
        odds_row("o_rr", ("Federer R.", "Nadal R."), day=1, Round="Round Robin"),
        odds_row("o_f", ("Federer R.", "Nadal R."), day=6, Round="The Final"),
    ]
    links, status = run(odds, sack)
    assert status.tolist() == ["matched", "matched"]
    assert links.loc["o_rr", "matchId"] == "rr" and links.loc["o_f", "matchId"] == "final"


def test_two_rows_claiming_one_match_make_a_conflict():
    """A duplicated odds row cannot link to an already claimed match."""
    odds = [odds_row("a", ("Federer R.", "Nadal R.")), odds_row("b", ("Federer R.", "Nadal R."))]
    _, status = run(odds, [sack_row("m1", FEDERER_NADAL)])
    assert sorted(status.tolist()) == ["conflict", "matched"]


def test_rate_table_excludes_out_of_coverage():
    """matchRate = matched / (matched + unmatched + conflict)."""
    frame = pd.DataFrame({"year": [2026] * 4, "status": ["matched", "unmatched", "out_of_coverage", "out_of_coverage"]})
    row = resolve.rate_table(frame, "year").loc[2026]
    assert row["matchRate"] == 0.5 and row["out_of_coverage"] == 2 and row["conflict"] == 0


def test_round_compatible_rules():
    """Named rounds must agree; numbered rounds fit any R-round but not RR."""
    assert resolve.round_compatible("The Final", "F")
    assert not resolve.round_compatible("Semifinals", "F")
    assert resolve.round_compatible("2nd Round", "R64")
    assert not resolve.round_compatible("1st Round", "RR")


def test_sackmann_keys_builds_keys_and_applies_remap():
    """Keys come from the players file; duplicate ids are remapped first."""
    matches = pd.DataFrame(
        {
            "tourney_id": ["2015-520"],
            "match_num": [1],
            "tourney_date": [MONDAY],
            "tourney_name": ["Roland Garros"],
            "round": ["F"],
            "winner_id": [9],
            "loser_id": [2],
            "winner_rank": [1],
            "loser_rank": [2],
        }
    )
    players = pd.DataFrame({"player_id": [1, 2], "name_first": ["Roger", "Rafael"], "name_last": ["Federer", "Nadal"]})
    frame = resolve.sackmann_keys(matches, players, {9: 1})
    assert frame.loc[0, "matchId"] == "2015-520-1"
    assert (frame.loc[0, "winnerKey"], frame.loc[0, "loserKey"]) == ("federer r", "nadal r")
