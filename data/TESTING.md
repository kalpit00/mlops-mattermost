## Testing the MLOps/moderation changes (simple checklist)

This repo has **two** main areas of change:

- **Go server path**: `server/channels/app/mlmoderation/*` (logging/features/scores/feedback)
- **Python data pipelines**: `data/pipelines/*` (synthetic, dataset build, monitoring, promotion gate), plus optional Docker Compose stack

Below are the simplest “does it run end-to-end?” checks you can do locally.

---

## 0) Quick sanity checks

From the repo root:

```bash
git status
```

- You should see your changed/new files listed (no surprises like a committed `.env`).

---

## 1) Python pipelines (fastest way to validate most of the work)

### 1.0 Enable uploads to your Chameleon MinIO (recommended)

Set these once in **PowerShell** before running the pipelines:

```bash
$env:MLOPS_SKIP_S3_UPLOAD="0"
$env:MLOPS_S3_ENDPOINT="http://129.114.27.107:9000"
$env:MLOPS_S3_ACCESS_KEY="admin"
$env:MLOPS_S3_SECRET_KEY="admin12345"
$env:MLOPS_S3_BUCKET="moderation-data"
```

### 1.1 Install Python deps

Requires **Python 3.11+**.

```bash
python -m pip install -r data/pipelines/requirements.txt
```

### 1.2 Generate synthetic data (smoke test)

```bash
python -m data.pipelines.cli_synthetic
```

Expected result: it completes without errors and writes outputs under your local artifacts root (typically `data/artifacts/...` unless you changed `MLOPS_LOCAL_ARTIFACTS_ROOT`) and uploads to your MinIO bucket.

### 1.3 Build dataset (quality + lineage + manifest)

```bash
python -m data.pipelines.cli_dataset_build --strict
```

Expected result: it creates a `datasets/<date>/` folder with (at least):

- `manifest.json`
- `quality_report.json`
- `training_lineage.json`
- `train.parquet`, `val.parquet`, `eval.parquet`

### 1.4 Run monitoring (drift report smoke test)

```bash
python -m data.pipelines.cli_monitoring --fail-on-breach
```

Expected result: it writes a monitor report JSON; exit code should be 0 unless your config intentionally triggers a breach.

### 1.5 Promotion gate (blocks/permits based on reports)

Point the gate at the dataset you just built by setting one env var (PowerShell shown):

```bash
$env:MLOPS_PROMOTION_QUALITY_REPORT="data/artifacts/datasets/<date>/quality_report.json"
python -m data.pipelines.cli_promotion_gate --print-json
```

Expected result: it prints JSON and exits with:

- `0` if promotion is allowed
- `1` if blocked (quality/drift rules)
- `2` if misconfigured (missing required paths)

---

## 2) Same Python checks via Makefile (optional convenience)

If you prefer short commands:

```bash
make mlops-install
make mlops-synthetic
make mlops-dataset
make mlops-monitor
```

---

## 3) Docker Compose stack (optional, validates container path + MinIO/Jupyter wiring)

### 3.1 Create `.env` for Compose

```bash
cp docker-compose-data.env.example .env
```

This repo’s example `.env` is already set to your Chameleon MinIO values. Keep `.env` gitignored (do **not** commit secrets).

### 3.2 Start MinIO + Jupyter (optional)

If you are using **Chameleon MinIO**, you do **not** need to run the local Compose `minio` service.

```bash
docker compose -f docker-compose-data.yml up -d jupyter
```

### 3.3 Run pipeline containers (one-off jobs)

```bash
docker compose -f docker-compose-data.yml --profile synthetic-dev run --rm mlops-synthetic
docker compose -f docker-compose-data.yml --profile mlops run --rm mlops-pipelines python -m data.pipelines.cli_monitoring --fail-on-breach
```

### 3.4 Stop the stack

```bash
docker compose -f docker-compose-data.yml down
```

---

## 4) Go server path (basic compile/smoke)

From the repo root:

```bash
go test ./server/channels/...
```

---

## 4.1) Start the full Mattermost app (local) + end-to-end smoke test

This checks the **real-time hooks** (online features/scores JSONL) and the **moderator feedback labels** (feedback JSONL).

### 4.1.1 Start Mattermost (dev mode)

Follow the standard Mattermost dev setup for your OS (database + server). Once you can access the web UI and create a team/channel, continue below.

### 4.1.2 Enable MLOps moderation logging (PowerShell)

From a PowerShell session where you will run the server:

```bash
$env:MM_MLMODERATION_ENABLE_ONLINE_FEATURES="true"
$env:MM_MLMODERATION_ENABLE_FEEDBACK_CAPTURE="true"
$env:MM_MLMODERATION_LOG_DIR="data/mlmoderation/logs"
$env:MM_MLMODERATION_FEEDBACK_LOG_DIR="data/mlmoderation/feedback"
```

Start the server the same way you normally do for local development.

### 4.1.3 Smoke check: post, flag, review, and confirm logs

- **Post a normal message** in a channel.
- **Flag** the post for review (content flagging flow).
- As a reviewer, choose either **Keep** or **Remove**.

Then verify these files exist and are being appended to (paths are repo-relative by default):

- `data/mlmoderation/logs/online_features_v1.jsonl`
- `data/mlmoderation/logs/online_scores_v1.jsonl`
- `data/mlmoderation/feedback/moderation_feedback_v1.jsonl`

If you see those files updating after each action, the end-to-end path is working.

---

## 5) What to do if something fails

- **Python import errors**: re-run `python -m pip install -r data/pipelines/requirements.txt`.
- **Docker errors**: confirm Docker Desktop is running; try `docker compose version`.
- **Promotion gate exits 2**: check your `MLOPS_PROMOTION_QUALITY_REPORT` path.

