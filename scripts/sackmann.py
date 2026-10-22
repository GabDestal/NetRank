"""Load and clean Sackmann ATP matches and players into graph-ready records.

Scope (decision log D14): tour-level matches (Grand Slams, Masters, other ATP events, Tour
Finals) dated 1991-01-01 or later. Davis Cup and Olympics are out. Walkovers are kept and
flagged; retirements are flagged.
"""

import logging
import math
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/sackmann")
FIRST_DATE = pd.Timestamp("1991-01-01")
TOUR_LEVELS = ("G", "M", "A", "F")
LEVEL_NAMES = {"G": "Grand Slam", "M": "Masters 1000", "A": "ATP Tour", "F": "Tour Finals"}

# Per-side CSV columns -> property names on the WON / LOST relationships.
SIDE_COLUMNS = {
    "rank": "rank",
    "rank_points": "rankPoints",
    "seed": "seed",
    "entry": "entry",
    "age": "age",
    "ace": "aces",
    "df": "doubleFaults",
    "svpt": "servePoints",
    "1stIn": "firstServesIn",
    "1stWon": "firstServeWon",
    "2ndWon": "secondServeWon",
    "SvGms": "serviceGames",
    "bpSaved": "breakPointsSaved",
    "bpFaced": "breakPointsFaced",
}
# Columns named winner_<x>/loser_<x> (the rest are w_<x>/l_<x>).
LONG_PREFIX = {"rank", "rank_points", "seed", "entry", "age"}

WALKOVER = re.compile(r"W/O|Walkover", re.IGNORECASE)
RETIRED = re.compile(r"RET|DEF|Def\.", re.IGNORECASE)

log = logging.getLogger(__name__)


def clean(value):
    """Turn pandas missing values into None and numpy scalars into Python scalars."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA:
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def collapse_spaces(text: str) -> str:
    """Trim and collapse runs of whitespace ('Joaquin  Aguilar' -> 'Joaquin Aguilar')."""
    return re.sub(r"\s+", " ", text).strip()


def read_matches(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Read every yearly file and keep in-scope matches only."""
    frames = [pd.read_csv(path, low_memory=False) for path in sorted(raw_dir.glob("atp_matches_[0-9]*.csv"))]
    matches = pd.concat(frames, ignore_index=True)
    matches["tourney_date"] = pd.to_datetime(matches["tourney_date"].astype(str), format="%Y%m%d")
    in_scope = matches["tourney_level"].isin(TOUR_LEVELS) & (matches["tourney_date"] >= FIRST_DATE)
    log.info(f"matches: {len(matches)} read, {int(in_scope.sum())} in scope")
    kept = matches[in_scope].reset_index(drop=True)
    kept.attrs.update(files=len(frames), read=len(matches))
    return kept


def read_players(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Read the players file with a normalised full name."""
    players = pd.read_csv(raw_dir / "atp_players.csv", dtype={"wikidata_id": "string"}, low_memory=False)
    first = players["name_first"].fillna("")
    last = players["name_last"].fillna("")
    players["name"] = (first + " " + last).map(collapse_spaces)
    return players


def canonical_ids(players: pd.DataFrame, matches: pd.DataFrame) -> dict[int, int]:
    """Map duplicate player ids (same first name, last name and birth date) to one canonical id.

    The canonical id is the one with the most in-scope matches. Returns only remapped ids.
    """
    counts = pd.concat([matches["winner_id"], matches["loser_id"]]).value_counts()
    used = players[players["player_id"].isin(counts.index)].copy()
    used["matches"] = used["player_id"].map(counts)
    remap = {}
    for _, group in used.dropna(subset=["dob"]).groupby(["name", "dob"]):
        if len(group) > 1:
            keep = int(group.sort_values("matches", ascending=False)["player_id"].iloc[0])
            for pid in group["player_id"]:
                if pid != keep:
                    remap[int(pid)] = keep
                    log.warning(f"duplicate player {group['name'].iloc[0]}: id {pid} merged into {keep}")
    return remap


def to_date(value) -> date | None:
    """Parse Sackmann's YYYYMMDD floats (e.g. 19860603.0) into a date, or None."""
    value = clean(value)
    if value is None:
        return None
    text = str(int(value))
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def player_records(players: pd.DataFrame, ids: Iterable[int]) -> list[dict]:
    """Player nodes for the given ids."""
    wanted = players[players["player_id"].isin(set(ids))]
    return [
        {
            "id": int(row.player_id),
            "name": row.name,
            "firstName": clean(row.name_first),
            "lastName": clean(row.name_last),
            "hand": clean(row.hand),
            "dob": to_date(row.dob),
            "ioc": clean(row.ioc),
            "height": clean(row.height),
            "wikidataId": clean(row.wikidata_id),
        }
        for row in wanted.itertuples(index=False)
    ]


def tournament_records(matches: pd.DataFrame) -> list[dict]:
    """One Tournament node per yearly edition (decision log D13)."""
    editions = matches.drop_duplicates("tourney_id")
    return [
        {
            "id": row.tourney_id,
            "name": collapse_spaces(row.tourney_name),
            "year": row.tourney_date.year,
            "startDate": row.tourney_date.date(),
            "level": row.tourney_level,
            "levelName": LEVEL_NAMES[row.tourney_level],
            "surface": clean(row.surface),
            "drawSize": clean(row.draw_size),
        }
        for row in editions.itertuples(index=False)
    ]


def side(row: pd.Series, who: str) -> dict:
    """Properties of one side of a match ('winner' or 'loser') for its WON / LOST relationship."""
    props = {}
    for column, prop in SIDE_COLUMNS.items():
        source = f"{who}_{column}" if column in LONG_PREFIX else f"{who[0]}_{column}"
        props[prop] = clean(row[source])
    return props


def match_records(matches: pd.DataFrame, remap: dict[int, int]) -> list[dict]:
    """Match nodes with their tournament and both players' relationship properties."""
    records = []
    for _, row in matches.iterrows():
        score = clean(row["score"]) or ""
        records.append(
            {
                "id": f"{row['tourney_id']}-{int(row['match_num'])}",
                "tournamentId": row["tourney_id"],
                "date": row["tourney_date"].date(),
                "round": row["round"],
                "bestOf": int(row["best_of"]),
                "score": score,
                "minutes": clean(row["minutes"]),
                "surface": clean(row["surface"]),
                "walkover": bool(WALKOVER.search(score)),
                "retired": bool(RETIRED.search(score)),
                "winnerId": remap.get(int(row["winner_id"]), int(row["winner_id"])),
                "loserId": remap.get(int(row["loser_id"]), int(row["loser_id"])),
                "winner": side(row, "winner"),
                "loser": side(row, "loser"),
            }
        )
    return records
