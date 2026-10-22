"""Unit tests for reading tennis-data files and turning odds into graph records."""

import pandas as pd
import pytest

from scripts import tennis_data


def odds_frame():
    """Two linked rows: one fully priced, one with a broken Pinnacle price and no market odds."""
    return pd.DataFrame(
        {
            "oddsRowId": ["f:0", "f:1"],
            "status": ["matched", "matched"],
            "method": ["exact", "exact"],
            "B365W": [1.5, 2.0],
            "B365L": [2.5, 1.8],
            "PSW": [1.55, 0.0],
            "PSL": [2.6, 1.9],
            "MaxW": [1.6, None],
            "MaxL": [2.7, None],
        }
    )


LINKS = pd.DataFrame(
    {
        "oddsRowId": ["f:0", "f:1"],
        "matchId": ["m0", "m1"],
        "method": ["exact", "surname_variant"],
        "dayOffset": [3, 9],
    }
)


def test_odds_prefixes_ignore_ranks_sets_and_points():
    """Only real price pairs are bookmaker prefixes."""
    columns = ["WRank", "LRank", "W1", "L1", "Wsets", "Lsets", "WPts", "LPts", "B365W", "B365L", "B&WW", "B&WL", "MaxW"]
    assert tennis_data.odds_prefixes(columns) == ["B&W", "B365"]


@pytest.mark.parametrize(
    ("winner", "loser", "expected"),
    [(1.5, 2.5, (1.5, 2.5)), ("1.5", "2.5", (1.5, 2.5)), (0, 2.5, None), (None, 2.5, None), ("n/a", 2.5, None)],
)
def test_decimal_pair_accepts_only_real_odds(winner, loser, expected):
    """Both prices must be numbers above 1.0."""
    assert tennis_data.decimal_pair({"XW": winner, "XL": loser}, "X") == expected


def test_price_records_compute_overround_and_count_skips():
    """PRICED rows per valid price; invalid prices are counted; market odds go on the match."""
    prices, market, skipped = tennis_data.price_records(odds_frame(), LINKS)
    by_key = {(p["matchId"], p["bookmaker"]): p for p in prices}
    assert set(by_key) == {("m0", "Bet365"), ("m0", "Pinnacle"), ("m1", "Bet365")}
    assert by_key[("m0", "Bet365")]["overround"] == round(1 / 1.5 + 1 / 2.5 - 1, 4)
    assert skipped["PS"] == 1 and skipped["EX"] == 0
    first, second = sorted(market, key=lambda m: m["matchId"])
    assert first["marketMaxWinnerOdds"] == 1.6 and second["marketMaxWinnerOdds"] is None
    assert second["oddsLinkMethod"] == "surname_variant" and second["oddsDayOffset"] == 9


def test_read_odds_parses_files_and_drops_cross_file_repeats(tmp_path):
    """Dates parse, names get keys, row ids are stable, and a row repeated across files is dropped."""
    row = {
        "Date": "2015-06-03",
        "Tournament": "French Open",
        "Winner": " Federer R. ",
        "Loser": "Nadal R.",
        "B365W": 1.5,
    }
    pd.DataFrame([row]).to_excel(tmp_path / "2015.xlsx", index=False)
    pd.DataFrame([row, {**row, "Winner": "Ramos-Vinolas A."}]).to_excel(tmp_path / "2016.xlsx", index=False)
    odds = tennis_data.read_odds(tmp_path)
    assert len(odds) == 2
    assert odds["winnerKey"].tolist() == ["federer r", "ramos vinolas a"]
    assert odds["oddsRowId"].tolist() == ["2015.xlsx:0", "2016.xlsx:0"]
    assert odds["Date"].dt.year.tolist() == [2015, 2015]


def test_read_odds_explains_missing_files(tmp_path):
    """No files: a clear error pointing at the manual download."""
    with pytest.raises(FileNotFoundError, match="manually"):
        tennis_data.read_odds(tmp_path)
