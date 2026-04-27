# Serving subsystem (Mattermost toxicity moderation)

This directory contains the serving component for CPU deployment (Chameleon VM / Kubernetes).

## Goals
- Typical load: ~1 req/s, peak ~5 req/s.
- p95 target: <= 150 ms for `/score` under expected load.
- Non-blocking UX: failures return quickly (503), allowing Mattermost fallback behavior.
- Output: toxicity probability `P(toxic)` + policy action.

## Layout

```text
serving/
  app/
    main.py
    model_loader.py
    schemas.py
    policy.py
    logging_utils.py
  ray_serve/
    app.py
    deploy_config.yaml
  benchmarks/
    benchmark_http.py
    benchmark_ray_serve.py
    sample_requests.jsonl
  tests/
    test_api.py
    test_policy.py
  Dockerfile
  requirements.txt
  README.md
```

## Tech stack
- API: FastAPI + Uvicorn
- Inference: scikit-learn pipeline loaded via joblib
- Metrics: Prometheus client + `prometheus-fastapi-instrumentator`
- Optional distributed serving: Ray Serve
- Tests: pytest + FastAPI TestClient
- Benchmarks: async HTTP load generator via httpx

## API contract
- `POST /score`:
  - input: `{text, channel_type?, prior_violation_count?}`
  - output: `{toxicity_score, model_version, policy_action, degraded}`
- `GET /health`, `GET /ready`

`toxicity_score` and `model_version` remain compatible with existing Mattermost integration.

## Policy mapping
- `allow`: score < `POLICY_REVIEW_THRESHOLD` (default `0.70`)
- `review`: `POLICY_REVIEW_THRESHOLD` <= score < `POLICY_ESCALATE_THRESHOLD` (default `0.90`)
- `escalate`: score >= `POLICY_ESCALATE_THRESHOLD`

## Graceful failure behavior
- If model is not loaded or inference errors, `/score` returns HTTP 503 quickly.
- Mattermost already has fallback handling in its Go moderation scorer when inference is unavailable.

## Local run

```bash
# from repo root
python -m pip install -r serving/requirements.txt
MODEL_PATH=/abs/path/to/pipeline.joblib \
SERVING_MODEL_VERSION=tfidf-logreg \
uvicorn serving.app.main:app --host 0.0.0.0 --port 8000
```

## Ray Serve run (optional)

```bash
ray start --head
serve run serving.ray_serve.app:toxicity_app
```

## Benchmarks

```bash
python -m serving.benchmarks.benchmark_http --url http://127.0.0.1:8000/score --requests 500 --concurrency 10
python -m serving.benchmarks.benchmark_ray_serve --url http://127.0.0.1:8001/ --requests 500 --concurrency 10
```

## Tests

```bash
pytest -q serving/tests
```

## Monitoring and promotion/rollback triggers
This serving layer emits model output and operational metrics:
- request status counters
- latency histogram
- toxicity score distribution
- predicted label/action counters

User feedback is captured upstream in Mattermost moderation feedback logs and consumed by pipeline gates.
Promotion/rollback gating is implemented in:
- `mlops_data/pipelines/monitoring.py`
- `mlops_data/pipelines/promotion_gate.py`

Those gates can block promotion on drift, data-quality, and class-balance thresholds.
