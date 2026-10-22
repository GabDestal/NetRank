"""GET /api/predict."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.database.client import Neo4jClient, get_db
from app.models.common import error_responses
from app.models.players import Surface
from app.models.predict import Prediction
from app.services import predict

router = APIRouter(prefix="/api", tags=["prediction"])

Db = Annotated[Neo4jClient, Depends(get_db)]


@router.get("/predict", response_model=Prediction, responses=error_responses(400, 404, 503))
def get_prediction(
    db: Db,
    p1: Annotated[int, Query(description="Player 1 id.")],
    p2: Annotated[int, Query(description="Player 2 id.")],
    surface: Annotated[Surface | None, Query(description="Required unless match_id is given.")] = None,
    match_id: Annotated[str | None, Query(max_length=40, description="A past match between p1 and p2.")] = None,
) -> Prediction:
    """P(p1 beats p2) from graph features only (tagged "predicted").

    With match_id, the match is re-predicted as of its date (no leakage) and returned with the
    bookmakers' margin-free probabilities and the actual result (tagged "verified").
    """
    return predict.predict(db, p1, p2, surface, match_id)
