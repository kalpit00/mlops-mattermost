import os
import time
from typing import Any, Optional

import joblib
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
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
Instrumentator().instrument(app).expose(app)

toxicity_score_histogram = Histogram(
    "ml_serving_toxicity_score",
    "Distribution of toxicity scores returned by the model.",
    ["model_version"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
predictions_total = Counter(
    "ml_serving_predictions_total",
    "Total predictions by predicted label and model version.",
    ["label", "model_version"],
)
score_requests_total = Counter(
    "ml_serving_score_requests_total",
    "Total /score requests by status and model version.",
    ["status", "model_version"],
)
score_duration_seconds = Histogram(
    "ml_serving_score_duration_seconds",
    "Latency of /score requests.",
    ["model_version"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

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
    start = time.perf_counter()
    if _pipeline is None:
        score_requests_total.labels(status="model_not_loaded", model_version=_model_version).inc()
        raise HTTPException(status_code=503, detail="model not loaded")

    try:
        # Pipeline expects raw text input on the first step ("tfidf", ...).
        proba = _pipeline.predict_proba([req.text])
        if proba.shape[1] < 2:
            score_requests_total.labels(status="bad_model_output", model_version=_model_version).inc()
            raise HTTPException(status_code=500, detail="unexpected model output shape")

        toxic_p = float(proba[0, 1])
        label = "toxic" if toxic_p >= 0.7 else "non_toxic"
        toxicity_score_histogram.labels(model_version=_model_version).observe(toxic_p)
        predictions_total.labels(label=label, model_version=_model_version).inc()
        score_requests_total.labels(status="ok", model_version=_model_version).inc()
        return ScoreResponse(toxicity_score=toxic_p, model_version=_model_version)
    finally:
        score_duration_seconds.labels(model_version=_model_version).observe(time.perf_counter() - start)
