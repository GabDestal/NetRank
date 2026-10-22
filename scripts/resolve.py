"""Entity resolution: link each tennis-data odds row to at most one Sackmann match.

Every stage applies the same frame (decision log D22):
1. Date window: the odds date (match day) falls in [tourney_date + start, tourney_date + end]
   days. Sackmann's tourney_date is the start Monday; Slams and some Masters run two weeks.
2. Names: both players agree under the stage's name rule.
3. Tournament: among several candidates, prefer a compatible round, then the highest
   tournament-name similarity, then the most recent start date.

Name rules, tried in order on the rows earlier stages left unmatched:
- exact:            folded last name + first initial, for both players;
- surname_variant:  first surname token or space-free surname (Ramos-Vinolas ~ Ramos,
                    O Connell ~ Oconnell), initials still required;
- surname_only:     initials ignored (Dolgopolov O. ~ Alexandr Dolgopolov), accepted only when
                    exactly one candidate remains AND both players' ATP ranks agree across the
                    two sources (within max(5, 10%)). Without the rank check this rule links
                    brothers (Lapentti G. ~ Nicolas Lapentti, Blake T. ~ James Blake).
A Sackmann match is claimed at most once. Rows dated after the Sackmann cutoff are
'out_of_coverage' and excluded from the match rate.
"""

from difflib import SequenceMatcher

import pandas as pd

from scripts.names import fold, last_name, sackmann_key, surname_variants

WINDOW = (0, 16)
SACKMANN_CUTOFF = pd.Timestamp("2026-06-08")
TD_ROUNDS = {"The Final": "F", "Semifinals": "SF", "Quarterfinals": "QF", "Round Robin": "RR"}
STATUSES = ("matched", "unmatched", "conflict", "out_of_coverage")


def sackmann_keys(matches: pd.DataFrame, players: pd.DataFrame, remap: dict[int, int]) -> pd.DataFrame:
    """In-scope Sackmann matches with id, start date, tournament, round and both name keys."""
    keys = {int(row.player_id): sackmann_key(row.name_first, row.name_last) for row in players.itertuples(index=False)}
    frame = pd.DataFrame(
        {
            "matchId": matches["tourney_id"] + "-" + matches["match_num"].astype(int).astype(str),
            "tourneyDate": matches["tourney_date"],
            "tourneyName": matches["tourney_name"],
            "sackRound": matches["round"],
            "winnerId": matches["winner_id"].astype(int).map(lambda pid: remap.get(pid, pid)),
            "loserId": matches["loser_id"].astype(int).map(lambda pid: remap.get(pid, pid)),
            "winnerRank": matches["winner_rank"],
            "loserRank": matches["loser_rank"],
        }
    )
    frame["winnerKey"] = frame["winnerId"].map(keys)
    frame["loserKey"] = frame["loserId"].map(keys)
    return frame


def similarity(left, right) -> float:
    """Similarity in [0, 1] between two folded names."""
    return SequenceMatcher(None, fold(str(left)), fold(str(right))).ratio()


def round_compatible(td_round, sack_round) -> bool:
    """Named rounds must agree exactly; numbered rounds ('2nd Round') fit any R128..R16."""
    wanted = TD_ROUNDS.get(td_round)
    if wanted is None:
        return str(sack_round).startswith("R") and sack_round != "RR"
    return wanted == sack_round


def ranks_agree(td_rank, sack_rank) -> pd.Series:
    """Both ranks present and within max(5, 10% of the Sackmann rank) of each other."""
    td_rank = pd.to_numeric(td_rank, errors="coerce")
    sack_rank = pd.to_numeric(sack_rank, errors="coerce")
    tolerance = (sack_rank * 0.10).clip(lower=5)
    return ((td_rank - sack_rank).abs() <= tolerance).fillna(False)


def candidates(odds: pd.DataFrame, sack: pd.DataFrame, on: list[str], window: tuple[int, int]) -> pd.DataFrame:
    """Odds x Sackmann pairs agreeing on the `on` columns with the odds date inside the window."""
    pairs = odds.merge(sack, on=on, suffixes=("", "_s"))
    offset = (pairs["Date"] - pairs["tourneyDate"]).dt.days
    return pairs[(offset >= window[0]) & (offset <= window[1])].drop_duplicates(["oddsRowId", "matchId"])


def rank(pairs: pd.DataFrame) -> pd.DataFrame:
    """Score candidate pairs and sort best-first within each odds row."""
    pairs = pairs.copy()
    pairs["roundOk"] = [round_compatible(t, s) for t, s in zip(pairs["Round"], pairs["sackRound"])]
    pairs["tournamentSimilarity"] = [
        max(similarity(t, name), similarity(loc, name))
        for t, loc, name in zip(pairs["Tournament"], pairs["Location"], pairs["tourneyName"])
    ]
    return pairs.sort_values(
        ["oddsRowId", "roundOk", "tournamentSimilarity", "tourneyDate"], ascending=[True, False, False, False]
    )


def explode_variants(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (winner variant, loser variant) combination."""
    out = frame.assign(
        winnerVar=frame["winnerKey"].map(lambda k: sorted(surname_variants(k))),
        loserVar=frame["loserKey"].map(lambda k: sorted(surname_variants(k))),
    )
    return out.explode("winnerVar").explode("loserVar")


def with_surnames(frame: pd.DataFrame) -> pd.DataFrame:
    """Add space-free surnames (initial dropped) for the surname_only rule."""
    return frame.assign(
        winnerSurname=frame["winnerKey"].map(lambda k: last_name(k).replace(" ", "")),
        loserSurname=frame["loserKey"].map(lambda k: last_name(k).replace(" ", "")),
    )


def stage_pairs(method: str, odds: pd.DataFrame, sack: pd.DataFrame, window: tuple[int, int]) -> pd.DataFrame:
    """Ranked candidate pairs for one name rule."""
    if method == "exact":
        pairs = candidates(odds, sack, ["winnerKey", "loserKey"], window)
    elif method == "surname_variant":
        pairs = candidates(explode_variants(odds), explode_variants(sack), ["winnerVar", "loserVar"], window)
    else:
        pairs = candidates(with_surnames(odds), with_surnames(sack), ["winnerSurname", "loserSurname"], window)
        pairs = pairs[pairs.groupby("oddsRowId")["matchId"].transform("nunique") == 1]
        both_agree = ranks_agree(pairs["WRank"], pairs["winnerRank"]) & ranks_agree(pairs["LRank"], pairs["loserRank"])
        pairs = pairs[both_agree]
    return rank(pairs) if not pairs.empty else pairs


def resolve(odds: pd.DataFrame, sack: pd.DataFrame, window: tuple[int, int] = WINDOW):
    """Return (links, odds with 'status' and 'method' columns).

    links: oddsRowId, matchId, method, roundOk, tournamentSimilarity, dayOffset.
    """
    odds = odds.copy()
    odds["status"] = "unmatched"
    odds["method"] = None
    odds.loc[odds["Date"] > SACKMANN_CUTOFF, "status"] = "out_of_coverage"
    links = []
    claimed: set[str] = set()
    for method in ("exact", "surname_variant", "surname_only"):
        pending = odds[odds["status"] == "unmatched"]
        pairs = stage_pairs(method, pending, sack[~sack["matchId"].isin(claimed)], window)
        if pairs.empty:
            continue
        best = pairs.drop_duplicates("oddsRowId").sort_values(["roundOk", "tournamentSimilarity"], ascending=False)
        clash = best.duplicated("matchId")
        winners = best[~clash].assign(method=method, dayOffset=(best["Date"] - best["tourneyDate"]).dt.days)
        links.append(winners[["oddsRowId", "matchId", "method", "roundOk", "tournamentSimilarity", "dayOffset"]])
        claimed |= set(winners["matchId"])
        matched = odds["oddsRowId"].isin(winners["oddsRowId"])
        odds.loc[matched, "status"] = "matched"
        odds.loc[matched, "method"] = method
        odds.loc[odds["oddsRowId"].isin(best[clash]["oddsRowId"]), "status"] = "conflict"
    columns = ["oddsRowId", "matchId", "method", "roundOk", "tournamentSimilarity", "dayOffset"]
    all_links = pd.concat(links, ignore_index=True) if links else pd.DataFrame(columns=columns)
    return all_links, odds


def diagnose(odds: pd.DataFrame, sack: pd.DataFrame) -> dict[str, int]:
    """How many unmatched rows looser rules would catch (reported, never applied)."""
    unmatched = odds[odds["status"] == "unmatched"]
    swapped = sack.rename(columns={"winnerKey": "loserKey", "loserKey": "winnerKey"})
    return {
        "exact_names_window_minus2": int(
            candidates(unmatched, sack, ["winnerKey", "loserKey"], (-2, WINDOW[1]))["oddsRowId"].nunique()
        ),
        "winner_loser_swapped": int(
            candidates(unmatched, swapped, ["winnerKey", "loserKey"], WINDOW)["oddsRowId"].nunique()
        ),
    }


def rate_table(odds: pd.DataFrame, by: str) -> pd.DataFrame:
    """Counts per status and match rate grouped by `by`; out-of-coverage rows are not in the denominator."""
    counts = pd.crosstab(odds[by], odds["status"]).reindex(columns=list(STATUSES), fill_value=0)
    eligible = counts["matched"] + counts["unmatched"] + counts["conflict"]
    counts["matchRate"] = (counts["matched"] / eligible.where(eligible > 0)).round(4)
    return counts
