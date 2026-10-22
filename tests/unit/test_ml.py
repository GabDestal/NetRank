"""Unit tests for features, the served model, the training helpers and /api/predict (no services)."""

import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.config import Settings
from app.errors import GdsUnavailableError
from app.ml import features as F
from app.ml import model as M
from app.services import predict as predict_service
from scripts import report_model, train

DIM = len(F.EMBEDDING_FEATURES)
SNAPSHOT = F.Snapshot(
    cutoff=date(2020, 1, 1),
    prestige={1: 3.0, 2: 1.5},
    recent={1: 2.0},
    embeddings={1: [0.5] * DIM, 2: [0.25] * DIM},
)


def artifact(weights=None) -> dict:
    """A minimal valid model artifact."""
    return {
        "version": "logistic-test-0001",
        "kind": "logistic",
        "features": list(F.FEATURES),
        "weights": weights if weights is not None else [0.1] * len(F.FEATURES),
        "servingSnapshot": {"cutoff": "2026-06-09", "prestige": {"1": 3.0}, "recent": {}, "embeddings": {}},
    }


# --------------------------------------------------------------------------- features


def test_history_counts_and_smoothing():
    """Experience, surface win rate (smoothed) and head-to-head from recorded matches."""
    history = F.replay([
        {"winnerId": 1, "loserId": 2, "surface": "Clay"},
        {"winnerId": 1, "loserId": 2, "surface": "Clay"},
        {"winnerId": 2, "loserId": 1, "surface": "Hard"},
    ])
    values = history.features(1, 2, "Clay")
    assert values["headToHead"] == 1.0 and values["headToHeadShare"] == pytest.approx(3 / 5 - 0.5)
    assert values["surfaceWinRate"] == pytest.approx(3 / 4 - 1 / 4)
    assert values["logExperience"] == 0.0
    assert history.surface_rate(1, None) == 0.5


def test_features_are_antisymmetric():
    """Swapping p1 and p2 negates every feature, so the model cannot learn an ordering."""
    history = F.replay([{"winnerId": 1, "loserId": 2, "surface": "Hard"}])
    forward = F.feature_vector(SNAPSHOT, history, (1, 2), "Hard")
    backward = F.feature_vector(SNAPSHOT, history, (2, 1), "Hard")
    assert list(forward) == list(F.FEATURES)
    assert all(forward[name] == pytest.approx(-backward[name]) for name in F.FEATURES)


def test_unseen_players_are_flagged_not_silently_zero():
    """A player absent from the snapshot gets the base PageRank, zero embedding and an indicator."""
    values = F.snapshot_features(SNAPSHOT, 1, 99)
    assert values["unseen"] == -1.0 and values["inactiveRecently"] == -1.0
    assert values["logPrestige"] == pytest.approx(math.log(3.0) - math.log(F.BASE_PAGERANK))
    assert values["fastrp00"] == 0.5


def test_devig_and_season_cutoff():
    """Margin removal normalises inverse odds; the snapshot cutoff is Jan 1 of the season."""
    assert F.devig(1.5, 2.5) == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.5))
    assert F.devig(2.0, 2.0) == 0.5
    assert F.season_cutoff(date(2019, 7, 1)) == date(2019, 1, 1)


# --------------------------------------------------------------------------- served model


def test_model_is_symmetric_and_explains_itself():
    """No intercept: P(p1 beats p2) + P(p2 beats p1) = 1; contributions group FastRP terms."""
    model = M.WinnerModel(artifact())
    history = F.replay([{"winnerId": 1, "loserId": 2, "surface": "Hard"}])
    forward = model.probability(F.feature_vector(SNAPSHOT, history, (1, 2), "Hard"))
    backward = model.probability(F.feature_vector(SNAPSHOT, history, (2, 1), "Hard"))
    assert forward + backward == pytest.approx(1.0)
    names = [c["feature"] for c in model.contributions(F.feature_vector(SNAPSHOT, history, (1, 2), "Hard"), top=20)]
    assert "fastrpEmbedding" in names and not any(n.startswith("fastrp0") for n in names)


def test_load_model_missing_and_mismatched(tmp_path):
    """No file, or a file for another feature layout, is a 503-class error."""
    with pytest.raises(GdsUnavailableError, match="make train"):
        M.load_model(str(tmp_path / "none.json"))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**artifact(), "features": ["other"]}), encoding="utf-8")
    with pytest.raises(GdsUnavailableError, match="does not match"):
        M.load_model(str(bad))
    good = tmp_path / "good.json"
    good.write_text(json.dumps(artifact()), encoding="utf-8")
    assert M.load_model(str(good)).snapshot.cutoff == date(2026, 6, 9)


# --------------------------------------------------------------------------- training helpers


def test_coin_flip_is_balanced_and_stable():
    """About half the winners become p1, and the flip depends only on the match id."""
    flips = [train.p1_is_winner(f"2019-{i}") for i in range(20000)]
    assert abs(sum(flips) / len(flips) - 0.5) < 0.01
    assert train.p1_is_winner("2019-7") == train.p1_is_winner("2019-7")


def test_split_and_orientation():
    """Seasons map to splits; odds and ranks follow the p1/p2 assignment."""
    assert [train.split_of(y) for y in (2018, 2019, 2021, 2022)] == ["train", "valid", "valid", "test"]
    assert train.oriented([1.5, 2.6], True) == (1.5, 2.6) and train.oriented([1.5, 2.6], False) == (2.6, 1.5)
    assert train.oriented(None, True) == (None, None)


def test_scores_and_rank_feature():
    """Metrics on a tiny example; missing ranks give a neutral feature."""
    result = train.scores([1, 0], [0.8, 0.3])
    assert result["accuracy"] == 1.0 and result["n"] == 2 and result["brier"] == pytest.approx(0.065)
    frame = pd.DataFrame({"rankP1": [10, None], "rankP2": [20, 5]})
    assert train.rank_feature(frame).ravel().tolist() == [pytest.approx(math.log(2)), 0.0]


def test_report_tables_and_plot(tmp_path, monkeypatch):
    """Markdown tables render and the calibration figure is written."""
    rows = {"Graph model": {"logLoss": 0.6, "brier": 0.2, "accuracy": 0.64, "n": 10}}
    assert "| Graph model | 0.6 | 0.2 | 0.64 | 10 |" in report_model.table(rows)
    rng = np.random.default_rng(0)
    labels = rng.integers(0, 2, 400)
    probabilities = {name: rng.random(400) for name in report_model.SERIES}
    curves = report_model.calibration_bins(labels, probabilities)
    monkeypatch.setattr(report_model, "FIGURE", tmp_path / "calibration.png")
    report_model.plot_calibration(curves, 400)
    assert (tmp_path / "calibration.png").stat().st_size > 10_000
    assert "->" in report_model.calibration_table(curves)


# --------------------------------------------------------------------------- /api/predict


FED = {"id": 1, "name": "Player One", "ioc": "SUI", "hand": "R", "dob": None}
NAD = {"id": 2, "name": "Player Two", "ioc": "ESP", "hand": "L", "dob": None}
MATCH = {
    "matchId": "2019-540-1", "date": date(2019, 7, 14), "surface": "Grass", "score": "7-6 6-1",
    "walkover": False, "retired": False, "winnerId": 2, "loserId": 1,
    "odds": [{"bookmaker": "Pinnacle", "winnerOdds": 1.8, "loserOdds": 2.1}],
}


@pytest.fixture(name="served")
def fixture_served(tmp_path, monkeypatch, fake_db_factory):
    """Model file on disk, snapshot building stubbed, fake database answering players/match/history."""
    path = tmp_path / "model.json"
    path.write_text(json.dumps(artifact()), encoding="utf-8")
    monkeypatch.setattr(predict_service, "get_settings", lambda: Settings(model_path=str(path)))
    monkeypatch.setattr(predict_service, "season_snapshot", lambda db, cutoff: SNAPSHOT)
    return fake_db_factory({
        "p.id IN [$p1, $p2]\nRETURN": [{"player": FED}, {"player": NAD}],
        "m.date < $before": [{"date": date(2018, 1, 1), "winnerId": 1, "loserId": 2, "surface": "Grass"}],
        "{id: $matchId}": [MATCH],
    })


def test_predict_now_is_tagged_and_versioned(api_client, served):
    """Future-style prediction: model probability tagged 'predicted', no market, history before the cutoff."""
    body = api_client.get("/api/predict", params={"p1": 1, "p2": 2, "surface": "Hard"}).json()
    assert body["prediction"]["tag"] == "predicted" and body["prediction"]["modelVersion"] == "logistic-test-0001"
    assert body["prediction"]["p1WinProbability"] + body["prediction"]["p2WinProbability"] == pytest.approx(1)
    assert body["market"] == [] and body["result"] is None and body["featuresBefore"] == "2026-06-09"
    history_params = next(p for q, p in served.calls if "m.date < $before" in q)
    assert history_params["before"] == date(2026, 6, 9)


@pytest.mark.usefixtures("served")
def test_predict_past_match_returns_market_and_result(api_client):
    """With match_id: features before the match date, margin-free odds and the result tagged 'verified'."""
    body = api_client.get("/api/predict", params={"p1": 1, "p2": 2, "match_id": "2019-540-1"}).json()
    assert body["featuresBefore"] == "2019-07-14" and body["surface"] == "Grass"
    market = body["market"][0]
    assert market["tag"] == "verified" and market["p1Odds"] == 2.1
    assert market["p1WinProbability"] == round(F.devig(2.1, 1.8), 4)
    assert body["result"]["winnerId"] == 2 and body["result"]["tag"] == "verified"


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"p1": 1, "p2": 2}, 400),                                  # no surface, no match
        ({"p1": 1, "p2": 1, "surface": "Hard"}, 400),               # same player
        ({"p1": 1, "p2": 2, "match_id": "2019-540-1", "surface": "Clay"}, 400),  # wrong surface
        ({"p1": 1, "p2": 2, "surface": "Sand"}, 422),
    ],
)
@pytest.mark.usefixtures("served")
def test_predict_rejects_bad_requests(api_client, params, status):
    """Inconsistent or invalid parameters."""
    assert api_client.get("/api/predict", params=params).status_code == status


def test_predict_without_model_is_503(api_client, fake_db_factory, monkeypatch, tmp_path):
    """No artifact: 503 telling to run make train."""
    fake_db_factory({})
    monkeypatch.setattr(predict_service, "get_settings", lambda: Settings(model_path=str(tmp_path / "x.json")))
    response = api_client.get("/api/predict", params={"p1": 1, "p2": 2, "surface": "Hard"})
    assert response.status_code == 503 and "make train" in response.json()["detail"]
