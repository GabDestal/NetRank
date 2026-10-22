"""Unit tests for the exploration report built from small synthetic frames."""

import pandas as pd

from scripts import report

ODDS = pd.DataFrame(
    {
        "oddsRowId": ["a", "b", "c"],
        "Date": pd.to_datetime(["2015-06-03", "2015-06-04", "2026-07-01"]),
        "sourceFile": ["2015.xlsx", "2015.xlsx", "2026.xlsx"],
        "Series": ["Grand Slam"] * 3,
        "Tournament": ["French Open"] * 3,
        "Round": ["1st Round"] * 3,
        "Winner": ["Federer R.", "Bu Y.", "Sinner J."],
        "Loser": ["Nadal R.", "Nadal R.", "Alcaraz C."],
        "winnerKey": ["federer r", "bu y", "sinner j"],
        "loserKey": ["nadal r", "nadal r", "alcaraz c"],
        "WRank": [1, 300, 1],
        "LRank": [2, 2, 2],
        "B365W": [1.5, 3.0, 1.8],
        "B365L": [2.5, 1.4, 2.0],
        "status": ["matched", "unmatched", "out_of_coverage"],
        "method": ["exact", None, None],
    }
)
LINKS = pd.DataFrame(
    {
        "oddsRowId": ["a"],
        "matchId": ["m1"],
        "method": ["exact"],
        "roundOk": [True],
        "tournamentSimilarity": [1.0],
        "dayOffset": [2],
    }
)
SACK = pd.DataFrame(
    {
        "matchId": ["m1"],
        "tourneyDate": pd.to_datetime(["2015-06-01"]),
        "tourneyName": ["Roland Garros"],
        "sackRound": ["R128"],
        "winnerRank": [1],
        "loserRank": [2],
        "winnerKey": ["federer r"],
        "loserKey": ["nadal r"],
    }
)


def test_table_renders_markdown():
    """Index becomes the first column; missing values render empty."""
    text = report.table(pd.DataFrame({"n": [1, None]}, index=pd.Index(["x", "y"], name="k")))
    assert text.splitlines() == ["| k | n |", "| --- | --- |", "| x | 1.0 |", "| y |  |"]


def test_bookmaker_coverage_counts_seasons():
    """B365 prices every 2015 and 2026 row: two covered seasons, kept as Bet365."""
    coverage = report.bookmaker_coverage(ODDS)
    assert coverage.loc["B365", "kept as"] == "Bet365"
    assert coverage.loc["B365", "seasons >= 80%"] == 2


def test_rank_validation_by_method():
    """The one exact link has equal ranks on both sides."""
    result = report.rank_validation(LINKS, ODDS, SACK)
    assert result.loc["exact", "ranksEqual"] == 1.0


def test_build_and_logs(tmp_path, monkeypatch):
    """The report shows the odds-side rate without out-of-coverage rows; logs list the unmatched row."""
    matches = pd.DataFrame({"tourney_level": ["G"], "w_ace": [10]})
    raw = {
        "matches": matches,
        "sack": SACK,
        "remap": {},
        "files": 1,
        "read": 1,
        "players": 2,
        "walkovers": 0,
        "retired": 0,
    }
    stats = {"PRICED loaded": {"Bet365": 1}, "invalid prices skipped": {"Bet365": 0}}
    text = report.build(raw, ODDS, LINKS, stats)
    assert "**Match rate (odds side): 50.00%** of 2 in-coverage rows; 1 rows out of coverage." in text
    assert "| Bu Y. | 1 |" in text
    monkeypatch.setattr(report, "LOG_DIR", tmp_path)
    report.write_logs(ODDS, LINKS)
    assert pd.read_csv(tmp_path / "unmatched.csv")["oddsRowId"].tolist() == ["b"]
