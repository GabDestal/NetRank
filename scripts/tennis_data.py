"""Read tennis-data.co.uk yearly ATP files (downloaded manually, see README).

The files are not fetched by any script: tennis-data.co.uk forbids automated downloads.
Each yearly workbook has one data sheet; odds come as <BOOKMAKER>W / <BOOKMAKER>L column pairs
whose set changes over the years.
"""

import logging
import re
from pathlib import Path

import pandas as pd

from scripts.names import tennisdata_key

RAW_DIR = Path("data/raw/tennis_data")
# Bookmakers kept as nodes: >= 10 seasons of coverage (decision log D23). Max/Avg are market
# aggregates and go on the Match instead; shorter-lived books and Betfair Exchange are dropped.
BOOKMAKERS = {"B365": "Bet365", "PS": "Pinnacle", "EX": "Expekt", "LB": "Ladbrokes"}
MARKET = {"Max": "marketMax", "Avg": "marketAvg"}
# Columns that end in W/L but are not odds.
NOT_ODDS = {"Wsets", "Lsets", "WRank", "LRank", "WPts", "LPts"}
SET_COLUMN = re.compile(r"^[WL]\d$")

log = logging.getLogger(__name__)


def odds_prefixes(columns) -> list[str]:
    """Bookmaker/aggregate prefixes that have both a W and an L column (e.g. 'B365', 'PS', 'Max')."""
    names = {str(c) for c in columns}
    return sorted(
        name[:-1]
        for name in names
        if name.endswith("W") and name not in NOT_ODDS and not SET_COLUMN.match(name) and f"{name[:-1]}L" in names
    )


def read_year(path: Path) -> pd.DataFrame:
    """First sheet of one yearly workbook, tagged with its source file."""
    frame = pd.read_excel(path, sheet_name=0)
    frame["sourceFile"] = path.name
    return frame


def read_odds(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """All yearly files, with parsed dates, name keys and a stable row id.

    Rows repeated across two yearly files (same date, players and tournament) are dropped.
    """
    paths = sorted(raw_dir.glob("20[0-9][0-9].xls*"))
    if not paths:
        raise FileNotFoundError(f"No tennis-data files in {raw_dir}: download them manually (see README).")
    odds = pd.concat([read_year(path) for path in paths], ignore_index=True)
    odds["Date"] = pd.to_datetime(odds["Date"])
    odds["Winner"] = odds["Winner"].astype(str).str.strip()
    odds["Loser"] = odds["Loser"].astype(str).str.strip()
    before = len(odds)
    odds = odds.drop_duplicates(["Date", "Winner", "Loser", "Tournament"]).reset_index(drop=True)
    if before != len(odds):
        log.warning(f"tennis-data: {before - len(odds)} rows repeated across yearly files dropped")
    odds["winnerKey"] = odds["Winner"].map(tennisdata_key)
    odds["loserKey"] = odds["Loser"].map(tennisdata_key)
    odds["oddsRowId"] = odds["sourceFile"] + ":" + odds.groupby("sourceFile").cumcount().astype(str)
    log.info(f"tennis-data: {len(odds)} rows from {len(paths)} files")
    return odds


def decimal_pair(row, prefix: str) -> tuple[float, float] | None:
    """(winner, loser) decimal odds for one prefix, or None unless both are numbers above 1.0."""
    winner = pd.to_numeric(row.get(f"{prefix}W"), errors="coerce")
    loser = pd.to_numeric(row.get(f"{prefix}L"), errors="coerce")
    if pd.isna(winner) or pd.isna(loser) or winner <= 1.0 or loser <= 1.0:
        return None
    return float(winner), float(loser)


def price_records(odds: pd.DataFrame, links: pd.DataFrame) -> tuple[list[dict], list[dict], dict[str, int]]:
    """PRICED rows per kept bookmaker, market/provenance rows per Match, and skip counts.

    overround = 1/winnerOdds + 1/loserOdds - 1 (the bookmaker margin; 0 for a fair book).
    """
    linked = odds.drop(columns=["method", "status"], errors="ignore").merge(links, on="oddsRowId")
    prices, market = [], []
    skipped = {code: 0 for code in BOOKMAKERS}
    for _, row in linked.iterrows():
        for code, name in BOOKMAKERS.items():
            pair = decimal_pair(row, code)
            if pair is None:
                if pd.notna(row.get(f"{code}W")):  # a price was there but is not valid odds
                    skipped[code] += 1
                continue
            prices.append(
                {
                    "matchId": row["matchId"],
                    "bookmaker": name,
                    "winnerOdds": pair[0],
                    "loserOdds": pair[1],
                    "overround": round(1 / pair[0] + 1 / pair[1] - 1, 4),
                }
            )
        entry = {
            "matchId": row["matchId"],
            "oddsLinkMethod": row["method"],
            "oddsDayOffset": int(row["dayOffset"]),
            "oddsSourceRow": row["oddsRowId"],
        }
        for prefix, prop in MARKET.items():
            pair = decimal_pair(row, prefix)
            entry[f"{prop}WinnerOdds"], entry[f"{prop}LoserOdds"] = pair if pair else (None, None)
        market.append(entry)
    return prices, market, skipped
