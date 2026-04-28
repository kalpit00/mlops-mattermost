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

## How Kubernetes / FastAPI gets the model (ArgoCD uses the same manifests)

The **FastAPI process never downloads** the joblib. A **single `emptyDir` volume** is mounted at `/models` for both the init container and the `api` container. Sources of truth in-repo: `infrastructure/k8s/apps/serving/serving.yaml`, `infrastructure/helm/mlops-stack/templates/serving.yaml`.

1. **MLflow model registry (which version):** Init container `fetch-model` runs Python with `MlflowClient` against `MLFLOW_TRACKING_URI` (e.g. `http://mlflow.platform.svc.cluster.local:5000`). It calls `get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)` — e.g. model **`tfidf_logreg`** alias **`production`** — and gets the resolved **`run_id`**.
2. **MinIO (artifact bytes):** It then calls `mlflow.artifacts.download_artifacts(run_id=..., artifact_path=MODEL_ARTIFACT_PATH, dst_path=/models)`. MLflow returns artifact locations like `s3://mlflow-artifacts/...`; the client reads object data from **MinIO** using `MLFLOW_S3_ENDPOINT_URL` and credentials from **`minio-secret`** (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`). So: **registry metadata from MLflow, file bytes from MinIO** (same pattern ArgoCD-synced clusters use).
3. **FastAPI / Uvicorn container:** Only `volumeMounts` `/models` and env **`MODEL_PATH=/models/tfidf_logreg_pipeline.joblib`**. The image (`Dockerfile.serving`) has `WORKDIR /app`, copies `serving/app` → `./app`, and runs `uvicorn app.main:app` on port **8000**. Inference code is `serving/app/model_loader.py` → `joblib.load(MODEL_PATH)`.

**Ray Serve** uses the same loader and env vars; it only needs a **filesystem path** to that same file. For ad-hoc tests on the cluster node, copy the file out of a healthy pod (see below).

## Model artifact (`tfidf_logreg_pipeline.joblib`)

The pipeline file is **not** stored in git. Real locations used in this project:

| Where | Path |
|--------|------|
| **Default in code** (if `MODEL_PATH` is unset) | `/models/tfidf_logreg_pipeline.joblib` — same as the `ml-serving` pod after its initContainer downloads the artifact (`infrastructure/k8s/apps/serving/serving.yaml`) |
| **After local training** (`training/train.py`) | `<repo>/training/outputs/tfidf_logreg_pipeline.joblib` |
| **Copy from running `ml-serving` pod** (same bytes as MLflow→MinIO init) | `POD=$(kubectl -n mlops-serving get pods -l app=ml-serving -o jsonpath='{.items[0].metadata.name}')` then `kubectl -n mlops-serving cp "$POD:/models/tfidf_logreg_pipeline.joblib" ./tfidf_logreg_pipeline.joblib` |

On a VM (example repo `/home/cc/mlops-mattermost`), pick **one** of:

```bash
# A) You already trained in this clone — use training output (create it by running training if missing)
export MODEL_PATH=/home/cc/mlops-mattermost/training/outputs/tfidf_logreg_pipeline.joblib

# B) Match the in-cluster layout — place the file on disk, then use the default path
sudo mkdir -p /models
sudo cp /home/cc/mlops-mattermost/training/outputs/tfidf_logreg_pipeline.joblib /models/tfidf_logreg_pipeline.joblib
unset MODEL_PATH   # optional; default is /models/tfidf_logreg_pipeline.joblib in serving/app/model_loader.py

# C) Copied artifact next to the repo
export MODEL_PATH=/home/cc/mlops-mattermost/tfidf_logreg_pipeline.joblib
```

Do **not** use a placeholder like `/path/to/tfidf_logreg_pipeline.joblib`; export a path that exists (`test -f "$MODEL_PATH"`).

## Local run

```bash
# from repo root (e.g. /home/cc/mlops-mattermost)
export PYTHONPATH="$(pwd)"
python -m pip install -r serving/requirements.txt
export MODEL_PATH="${MODEL_PATH:-/models/tfidf_logreg_pipeline.joblib}"
export SERVING_MODEL_VERSION=tfidf-logreg
uvicorn serving.app.main:app --host 0.0.0.0 --port 8000
```

## Ray Serve run (optional)

Run from **repository root** so `serving.ray_serve.app` imports correctly.

**Preferred when K8s FastAPI is already healthy** — copy the exact artifact the init container placed in `/models`:

```bash
cd ~/mlops-mattermost
mkdir -p .cache
POD=$(kubectl -n mlops-serving get pods -l app=ml-serving -o jsonpath='{.items[0].metadata.name}')
kubectl -n mlops-serving cp "$POD:/models/tfidf_logreg_pipeline.joblib" .cache/tfidf_logreg_pipeline.joblib
export MODEL_PATH="$(pwd)/.cache/tfidf_logreg_pipeline.joblib"
```

Then start Ray (venv optional):

```bash
cd ~/mlops-mattermost
source .venv-serving/bin/activate 2>/dev/null || true
export PYTHONPATH="$(pwd)"
export SERVING_MODEL_VERSION=tfidf-logreg
test -f "$MODEL_PATH" || { echo "Set MODEL_PATH to an existing joblib"; exit 1; }

ray start --head --dashboard-host=0.0.0.0
serve run serving.ray_serve.app:toxicity_app
```

**Smoke-test** (Ray ingress is usually `POST /` on the proxy port, often **8000** — confirm in `serve run` logs if unsure):

```bash
curl -sS -X POST "http://127.0.0.1:8000/" -H 'Content-Type: application/json' \
  -d '{"text":"hello","channel_type":"O","prior_violation_count":0}'
```

FastAPI in-cluster remains `POST http://ml-serving.mlops-serving.svc.cluster.local:8000/score` with the same JSON body.

### Duplicating FastAPI as a second container later

Reuse the **same** Deployment pattern: same `initContainers` + `emptyDir` + `MODEL_PATH=/models/...`, but replace the `api` container `command` with a Ray entrypoint (image must include `serving/ray_serve` and `PYTHONPATH` for `serving.*`, or use a dedicated Dockerfile). Two practical patterns: **(a)** second Deployment `ml-serving-ray` cloning the manifest with a different image/CMD/Service port; **(b)** second container in the same Pod sharing `/models` (more coupled).

### Troubleshooting Ray on the VM

**`ConnectionError: Ray is trying to start at ...:6379, but is already running`** — You already have a local Ray head. Either skip `ray start` and only run `serve run ...`, or reset and start clean:

```bash
ray stop --force
ray start --head --dashboard-host=0.0.0.0 --disable-usage-stats
```

**`MODEL_PATH does not exist: '/path/to/tfidf_logreg_pipeline.joblib'`** — Your shell still has a tutorial `export MODEL_PATH=...`. Run `unset MODEL_PATH` (the loader now ignores that exact placeholder and falls back to `/models/tfidf_logreg_pipeline.joblib`) or point at a real file:

```bash
env | grep -E '^MODEL_PATH='
unset MODEL_PATH
# then either put the joblib at /models/... (sudo) or:
export MODEL_PATH="$HOME/mlops-mattermost/.cache/tfidf_logreg_pipeline.joblib"
```

After changing env or code, **`ray stop --force`** then `ray start` + `serve run` again so Serve replicas pick up the new environment.

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
