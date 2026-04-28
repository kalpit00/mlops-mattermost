from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

from .logging_utils import get_logger, log_inference_event
from .model_loader import ModelConfig, ModelLoader
from .policy import PolicyConfig, map_score_to_action
from .schemas import HealthResponse, ScoreRequest, ScoreResponse

app = FastAPI(title="Mattermost ML Moderation Inference", version="0.2.0")
Instrumentator().instrument(app).expose(app)

logger = get_logger("serving.api")
model_cfg = ModelConfig.from_env()
policy_cfg = PolicyConfig.from_env()
loader = ModelLoader(model_cfg)

toxicity_score_histogram = Histogram(
    "ml_serving_toxicity_score",
    "Distribution of toxicity scores returned by the model.",
    ["model_version"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
predictions_total = Counter(
    "ml_serving_predictions_total",
    "Total predictions by predicted label and model version.",
    ["label", "policy_action", "model_version"],
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


@app.on_event("startup")
def startup() -> None:
    loader.load()
    logger.info("model_loaded", extra={"extra": {"model_path": model_cfg.model_path, "model_version": model_cfg.model_version}})


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if loader.is_loaded() else "degraded",
        model_loaded=loader.is_loaded(),
        model_version=loader.model_version,
    )


@app.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return health()


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest, request: Request) -> ScoreResponse:
    start = time.perf_counter()
    scenario = request.headers.get("X-Load-Scenario")
    text_length = len(req.text)

    def elapsed_ms() -> float:
        return (time.perf_counter() - start) * 1000.0

    if not loader.is_loaded():
        score_requests_total.labels(status="model_not_loaded", model_version=loader.model_version).inc()
        log_inference_event(
            backend="fastapi",
            status_code=503,
            latency_ms=elapsed_ms(),
            toxicity_score=None,
            action=None,
            endpoint="/score",
            error="model_not_loaded",
            extra={"text_length": text_length, "scenario": scenario, "model_version": loader.model_version},
        )
        raise HTTPException(status_code=503, detail="model not loaded")

    try:
        toxic_p = loader.score(req.text)
        policy_action = map_score_to_action(toxic_p, policy_cfg)
        label = "toxic" if toxic_p >= policy_cfg.review_threshold else "non_toxic"

        toxicity_score_histogram.labels(model_version=loader.model_version).observe(toxic_p)
        predictions_total.labels(label=label, policy_action=policy_action, model_version=loader.model_version).inc()
        score_requests_total.labels(status="ok", model_version=loader.model_version).inc()
        log_inference_event(
            backend="fastapi",
            status_code=200,
            latency_ms=elapsed_ms(),
            toxicity_score=toxic_p,
            action=policy_action,
            endpoint="/score",
            extra={"text_length": text_length, "scenario": scenario, "model_version": loader.model_version},
        )

        return ScoreResponse(
            toxicity_score=toxic_p,
            model_version=loader.model_version,
            policy_action=policy_action,
            degraded=False,
        )
    except HTTPException as exc:
        log_inference_event(
            backend="fastapi",
            status_code=exc.status_code,
            latency_ms=elapsed_ms(),
            toxicity_score=None,
            action=None,
            endpoint="/score",
            error=str(exc.detail),
            extra={"text_length": text_length, "scenario": scenario, "model_version": loader.model_version},
        )
        raise
    except Exception as exc:
        score_requests_total.labels(status="inference_error", model_version=loader.model_version).inc()
        logger.error("inference_error", extra={"extra": {"error": str(exc)}})
        log_inference_event(
            backend="fastapi",
            status_code=503,
            latency_ms=elapsed_ms(),
            toxicity_score=None,
            action=None,
            endpoint="/score",
            error="inference_error",
            extra={"text_length": text_length, "scenario": scenario, "model_version": loader.model_version},
        )
        # Graceful failure: explicit 503 lets Mattermost fallback path take over.
        raise HTTPException(status_code=503, detail="inference unavailable")
    finally:
        score_duration_seconds.labels(model_version=loader.model_version).observe(time.perf_counter() - start)
