"""Train and evaluate the match-outcome model (make train).

1. Build one row per played match from 1995: seeded random p1/p2, label "p1 won", leakage-free
   features (app/ml/features.py): a snapshot at Jan 1 of the match's season and history replayed
   strictly before the match date.
2. Split by date: train <= 2018, validation 2019-2021, test 2022 to the Sackmann cutoff.
3. Select on validation: logistic regression (C grid) vs gradient boosting (kept only if it beats
   logistic regression by >= 1% log loss).
4. Refit the chosen model on train + validation, then evaluate ONCE on test against Pinnacle, Bet365
   (margin removed) and a ranking baseline on exactly the same rows.
5. Export the logistic model and an as-of-now snapshot to models/winner_model.json; write
   docs/model_report.md and the calibration plot.
"""

import hashlib
import json
import logging
import zlib
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.config import get_settings
from app.database.client import Neo4jClient
from app.ml import features as F
from scripts import report_model

SEED = 42
FIRST_SEASON = 1995
TRAIN_LAST, VALID_LAST = 2018, 2021
C_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
GBM_MARGIN = 0.01
MODEL_PATH = Path("models/winner_model.json")

MATCHES = """
MATCH (w:Player)-[wr:WON]->(m:Match)<-[lr:LOST]-(l:Player)
RETURN m.id AS id, m.date AS date, m.surface AS surface, m.walkover AS walkover, m.retired AS retired,
       w.id AS winnerId, l.id AS loserId, wr.rank AS winnerRank, lr.rank AS loserRank,
       [(:Bookmaker {name: 'Pinnacle'})-[p:PRICED]->(m) | [p.winnerOdds, p.loserOdds]][0] AS pinnacle,
       [(:Bookmaker {name: 'Bet365'})-[p:PRICED]->(m) | [p.winnerOdds, p.loserOdds]][0] AS bet365
ORDER BY date, id
"""

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- dataset


def p1_is_winner(match_id: str) -> bool:
    """Seeded, per-match coin flip (stable whatever rows are filtered): is the winner listed as p1?"""
    return zlib.crc32(f"{SEED}:{match_id}".encode()) % 2 == 0


def split_of(season: int) -> str:
    """train / valid / test by season."""
    if season <= TRAIN_LAST:
        return "train"
    return "valid" if season <= VALID_LAST else "test"


def oriented(pair, p1_won: bool) -> tuple[float | None, float | None]:
    """(odds of p1, odds of p2) from a [winnerOdds, loserOdds] pair."""
    if not pair:
        return None, None
    return (pair[0], pair[1]) if p1_won else (pair[1], pair[0])


def make_row(match: dict, values: dict) -> dict:
    """Features plus label and the metadata used for evaluation (never used as features)."""
    p1_won = p1_is_winner(match["id"])
    ranks = (match["winnerRank"], match["loserRank"]) if p1_won else (match["loserRank"], match["winnerRank"])
    pin, b365 = oriented(match["pinnacle"], p1_won), oriented(match["bet365"], p1_won)
    return {
        **values,
        "label": int(p1_won),
        "matchId": match["id"],
        "date": match["date"],
        "season": match["date"].year,
        "split": split_of(match["date"].year),
        "retired": bool(match["retired"]),
        "rankP1": ranks[0],
        "rankP2": ranks[1],
        "pinnacleP1": pin[0],
        "pinnacleP2": pin[1],
        "bet365P1": b365[0],
        "bet365P2": b365[1],
    }


def build_dataset(db: Neo4jClient, matches: list[dict], first_season: int = FIRST_SEASON) -> pd.DataFrame:
    """Replay every match by date; emit a row for each played match from `first_season`."""
    history = F.History()
    snapshots: dict[date, F.Snapshot] = {}
    rows = []
    for day, group in groupby(matches, key=lambda m: m["date"]):
        played = [m for m in group if not m["walkover"]]
        if day.year >= first_season:
            cutoff = F.season_cutoff(day)
            if cutoff not in snapshots:
                log.info(f"snapshot {cutoff}")
                snapshots[cutoff] = F.build_snapshot(db, cutoff)
            for match in played:
                p1_won = p1_is_winner(match["id"])
                players = (match["winnerId"], match["loserId"]) if p1_won else (match["loserId"], match["winnerId"])
                rows.append(make_row(match, F.feature_vector(snapshots[cutoff], history, players, match["surface"])))
        for match in played:  # recorded only after every match of the day was scored
            history.record(match["winnerId"], match["loserId"], match["surface"])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- models


def logistic(c: float):
    """Scaled logistic regression without intercept (features are antisymmetric)."""
    return make_pipeline(
        StandardScaler(with_mean=False),
        LogisticRegression(C=c, fit_intercept=False, max_iter=5000, random_state=SEED),
    )


def gradient_boosting():
    """Gradient-boosted trees, fixed seed, no early stopping (deterministic)."""
    return HistGradientBoostingClassifier(random_state=SEED, learning_rate=0.05, max_iter=300, early_stopping=False)


def scores(y, p) -> dict:
    """Log loss, Brier score and accuracy for probabilities p of label 1."""
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return {
        "logLoss": round(float(log_loss(y, p, labels=[0, 1])), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "accuracy": round(float(accuracy_score(y, p > 0.5)), 4),
        "n": int(len(y)),
    }


def matrix(frame: pd.DataFrame) -> np.ndarray:
    """Feature matrix in FEATURES order."""
    return frame[list(F.FEATURES)].to_numpy(dtype=float)


def select_model(train: pd.DataFrame, valid: pd.DataFrame) -> tuple[dict, list[dict]]:
    """Validation-only model selection; returns the chosen spec and every candidate's scores."""
    x_train, y_train, x_valid, y_valid = matrix(train), train["label"], matrix(valid), valid["label"]
    candidates = []
    for c in C_GRID:
        model = logistic(c).fit(x_train, y_train)
        candidates.append({"model": "logistic", "C": c, **scores(y_valid, model.predict_proba(x_valid)[:, 1])})
    best_lr = min(candidates, key=lambda r: r["logLoss"])
    gbm = gradient_boosting().fit(x_train, y_train)
    candidates.append({"model": "gradient_boosting", "C": None, **scores(y_valid, gbm.predict_proba(x_valid)[:, 1])})
    gbm_wins = candidates[-1]["logLoss"] < best_lr["logLoss"] * (1 - GBM_MARGIN)
    chosen = {"model": "gradient_boosting"} if gbm_wins else {"model": "logistic", "C": best_lr["C"]}
    return chosen, candidates


def rank_feature(frame: pd.DataFrame) -> np.ndarray:
    """log(rank p2) - log(rank p1): positive when p1 is better ranked; 0 when a rank is missing."""
    r1, r2 = pd.to_numeric(frame["rankP1"]), pd.to_numeric(frame["rankP2"])
    value = np.log(r2) - np.log(r1)
    return value.fillna(0.0).to_numpy().reshape(-1, 1)


def fit_rank_baseline(train: pd.DataFrame):
    """One-feature logistic model on the rank ratio, fitted on training rows that have both ranks."""
    known = train["rankP1"].notna() & train["rankP2"].notna()
    return LogisticRegression(fit_intercept=False).fit(rank_feature(train[known]), train.loc[known, "label"])


# --------------------------------------------------------------------------- evaluation (test: once)


def bookmaker_probability(frame: pd.DataFrame, book: str) -> np.ndarray:
    """Margin-free probability that p1 wins from one bookmaker's odds."""
    return np.array([F.devig(o1, o2) for o1, o2 in zip(frame[f"{book}P1"], frame[f"{book}P2"])])


def predictors(frame: pd.DataFrame, model, rank_model) -> dict[str, np.ndarray]:
    """P(p1 wins) from the model, both bookmakers (margin removed) and the ranking baseline, same rows."""
    return {
        "Graph model": model.predict_proba(matrix(frame))[:, 1],
        "Pinnacle (no margin)": bookmaker_probability(frame, "pinnacle"),
        "Bet365 (no margin)": bookmaker_probability(frame, "bet365"),
        "Ranking baseline": rank_model.predict_proba(rank_feature(frame))[:, 1],
    }


def compare(frame: pd.DataFrame, model, rank_model) -> dict:
    """Scores of every predictor on the same rows."""
    return {name: scores(frame["label"], p) for name, p in predictors(frame, model, rank_model).items()}


def final_test(dataset: pd.DataFrame, chosen: dict) -> dict:
    """Refit on train + validation, then the single evaluation on the test seasons."""
    fit_rows = dataset[dataset["split"] != "test"]
    model = (logistic(chosen["C"]) if chosen["model"] == "logistic" else gradient_boosting()).fit(
        matrix(fit_rows), fit_rows["label"]
    )
    rank_model = fit_rank_baseline(dataset[dataset["split"] == "train"])
    test = dataset[dataset["split"] == "test"]
    priced = test["pinnacleP1"].notna() & test["bet365P1"].notna()
    common, retired = test[priced & ~test["retired"]], test[priced & test["retired"]]
    completed = test[~test["retired"]]
    return {
        "model": model,
        "common": compare(common, model, rank_model),
        "retired": compare(retired, model, rank_model),
        "allCompleted": scores(completed["label"], model.predict_proba(matrix(completed))[:, 1]),
        "calibration": {"labels": common["label"].to_numpy(), "probabilities": predictors(common, model, rank_model)},
        "seasons": (int(test["season"].min()), int(test["season"].max())),
        "lastDate": str(test["date"].max()),
    }


# --------------------------------------------------------------------------- export


def export(model, chosen: dict, serving: F.Snapshot, summary: dict) -> dict:
    """Write the JSON artifact read by the API (logistic regression only)."""
    if chosen["model"] != "logistic":
        raise RuntimeError("Only logistic regression can be served from JSON; add a serving path first.")
    scaler, regression = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
    weights = (regression.coef_[0] / scaler.scale_).round(10).tolist()
    digest = hashlib.sha256(json.dumps([list(F.FEATURES), weights]).encode()).hexdigest()[:8]
    created = datetime.now(timezone.utc)
    artifact = {
        "version": f"logistic-{created:%Y%m%d}-{digest}",
        "createdAt": created.isoformat(timespec="seconds"),
        "kind": "logistic",
        "features": list(F.FEATURES),
        "weights": weights,
        "standardisedWeights": dict(zip(F.FEATURES, regression.coef_[0].round(6).tolist())),
        "trainedOn": {"firstSeason": FIRST_SEASON, "lastSeason": VALID_LAST, "C": chosen["C"], "seed": SEED},
        "metrics": summary,
        "servingSnapshot": {
            "cutoff": serving.cutoff.isoformat(),
            "prestige": serving.prestige,
            "recent": serving.recent,
            "embeddings": {k: [round(x, 6) for x in v] for k, v in serving.embeddings.items()},
        },
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact


def main() -> None:
    """Build, select, test once, export and report."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Neo4jClient.from_settings(get_settings())
    try:
        matches = db.read(MATCHES)
        dataset = build_dataset(db, matches)
        train, valid = dataset[dataset["split"] == "train"], dataset[dataset["split"] == "valid"]
        log.info(f"rows: {dataset['split'].value_counts().to_dict()}; p1 won rate {dataset['label'].mean():.4f}")
        chosen, candidates = select_model(train, valid)
        log.info(f"validation: chosen {chosen}")
        reference = fit_rank_baseline(train).predict_proba(rank_feature(valid))[:, 1]
        reference_scores = scores(valid["label"], reference)
        candidates.append({"model": "ranking baseline (reference only)", "C": None, **reference_scores})
        result = final_test(dataset, chosen)
        serving_cutoff = max(m["date"] for m in matches) + timedelta(days=1)
        serving = F.build_snapshot(db, serving_cutoff)
        summary = {"test": result["common"], "validation": candidates}
        artifact = export(result["model"], chosen, serving, summary)
        report_model.write(dataset, chosen, candidates, result, artifact)
        log.info(f"model {artifact['version']} written to {MODEL_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
