import os
from typing import Any, Optional

import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


MODEL_PATH = os.environ.get("MODEL_PATH", "/models/tfidf_logreg_pipeline.joblib").strip()


class ScoreRequest(BaseModel):
    text: str = Field(..., min_length=1)
    channel_type: Optional[str] = None
    prior_violation_count: Optional[int] = None


class ScoreResponse(BaseModel):
    toxicity_score: float
    model_version: str


app = FastAPI(title="Mattermost ML Moderation Inference", version="0.1.0")

_pipeline: Any = None
_model_version: str = "unknown"


@app.on_event("startup")
def _load_model() -> None:
    global _pipeline, _model_version
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"MODEL_PATH does not exist: {MODEL_PATH}")
    _pipeline = joblib.load(MODEL_PATH)
    _model_version = os.environ.get("SERVING_MODEL_VERSION", "tfidf-logreg").strip() or "tfidf-logreg"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    # Pipeline expects raw text input on the first step ("tfidf", ...).
    proba = _pipeline.predict_proba([req.text])
    if proba.shape[1] < 2:
        raise HTTPException(status_code=500, detail="unexpected model output shape")

    toxic_p = float(proba[0, 1])
    return ScoreResponse(toxicity_score=toxic_p, model_version=_model_version)
