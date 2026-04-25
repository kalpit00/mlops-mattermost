# MLOps data subsystem — milestone documentation

This document records the **integrated moderation / MLOps data track** added to this Mattermost repository: batch Python pipelines, runtime JSONL logging in Go, automation, and governance artifacts (manifests, quality, lineage, drift, promotion gate). It is the single “full changelog” for the data subsystem as delivered for milestone submission.

---

## 1. Goals

- **Transparency:** versioned manifests, schema tags, and JSON quality reports for every dataset build.
- **Accountability:** `training_lineage.json` listing input paths and SHA-256 hashes plus a non-secret config snapshot (no bulk raw text).
- **Privacy:** training exports strip inference leakage columns and a defined set of identifier / PII-like columns; exports are limited to an explicit column list.
- **Data quality checkpoints:** evaluate data quality at **ingestion** (external sources), at **training set compilation** (re-training dataset build), and monitor **live inference** data quality + drift in production.
- **Robustness:** dataset build can **abort before writing parquet** when quality checks fail (`MLOPS_DATASET_FAIL_ON_QUALITY`, default on); CLI `--no-fail-on-quality` for local experiments.
- **Fairness (placeholder):** `quality_report.json` includes a `fairness` section (`fairness_slice_report_v0`) with optional eval slice × label counts when `MLOPS_DATASET_FAIRNESS_SLICES` lists existing columns.
- **Promotion / rollback:** `cli_promotion_gate` exits non-zero if training quality failed, eval label imbalance is below threshold, or monitoring reports drift breaches.

---

## 2. Repository layout (data-related)

| Location | Purpose |
|----------|---------|
| `data/README.md` | **Entry point** — flow diagram, commands, links (tracked; see `.gitignore` exception). |
| `data/__init__.py` | Python package marker for `data.pipelines`. |
| `data/pipelines/` | All batch pipeline **source** (tracked). |
| `data/artifacts/` | **Gitignored** — Jigsaw, synthetic outputs, `datasets/{date}/`. |
| `data/mlmoderation/` | **Gitignored** — server-written logs and monitoring outputs. |
| `server/channels/app/mlmoderation/` | **Go** — online features, scores, feedback capture. |
| `docker-compose-data.yml` | MinIO + Jupyter + Compose profiles for pipeline containers. |
| `docker-compose-data.env.example` | Template for `.env` (secrets **not** committed). |
| `Dockerfile.pipelines` | Slim Python image for `python -m data.pipelines.*`. |
| `Makefile` | `make mlops-*` shortcuts. |
| `.github/workflows/mlops-data-pipelines.yml` | Scheduled + manual CI. |
| `infrastructure/kubernetes/mlops-data/` | K8s manifests + README (MinIO/Jupyter + stub CronJobs). |

**Non-duplication rule:** One primary stack per environment — e.g. use either **Compose** or **Kubernetes** MinIO for a given deployment, not two uncoordinated buckets. The K8s README calls out overlap with `platform` MinIO.

---

## 3. Python pipelines (`data/pipelines/`)

| File | Role |
|------|------|
| `__init__.py` | Lazy exports for optional deps. |
| `__main__.py` | Default CLI alias (Jigsaw). |
| `requirements.txt` | `boto3`, `numpy`, `pandas`, `pyarrow`. |
| `jigsaw_ingestion.py` + `cli_jigsaw.py` | Jigsaw CSV → binary parquet + manifest; S3/MinIO optional; env empty-string handling for `MLOPS_LOCAL_ARTIFACTS_ROOT`. |
| `synthetic_messages.py` + `cli_synthetic.py` | Synthetic Post-shaped data; artifact and/or HTTP; same env hygiene for artifacts root. |
| `dataset_build.py` + `cli_dataset_build.py` | Thread-safe time splits; **v2** quality schema; **lineage** file; **privacy strips**; `--no-fail-on-quality`. |
| `monitoring.py` + `cli_monitoring.py` | Ingestion / training / live drift; JSON + optional parquet summary; `promotion_integration` hint in report. |
| `promotion_gate.py` + `cli_promotion_gate.py` | Promotion blocker from quality + monitor paths + eval balance. |

**Dataset build outputs (per `datasets/{dataset_date}/`):**

- `train.parquet`, `val.parquet`, `eval.parquet`
- `manifest.json` — `manifest_schema_version: dataset_manifest_v2`, `build_id`, column list, privacy note, paths to reports/lineage
- `quality_report.json` — `schema_version: dataset_quality_v2`, `blocking_codes`, thresholds, label balance, thread leakage, text empty rates, fairness block
- `training_lineage.json` — `schema_version: training_lineage_v1`, per-input SHA-256, row counts, config snapshot

**Key environment variables (non-exhaustive):** `MLOPS_*` prefixes on ingest, synthetic, dataset, monitor, and promotion modules — see each `from_env()`.

---

## 4. Go runtime (`server/channels/app/mlmoderation/`)

Implements schema-versioned JSONL for:

- Online feature rows (drift / debugging)
- Model scores
- Moderation feedback for retraining

Wired from the app layer on post save and content-flagging outcomes (keep/remove). Documented in `server/channels/app/mlmoderation/README.md`.

---

## 5. Secrets and security

- **Never commit:** `.env`, production MinIO/Jupyter passwords, Mattermost tokens, cloud keys.
- **Compose:** `docker-compose-data.env.example` supplies **placeholder** values; developers copy to `.env` (gitignored).
- **CI:** GitHub Actions uses `secrets.*` / `vars.*`; workflow only exports non-empty vars into `GITHUB_ENV` to avoid clobbering Python defaults.
- **Removed from Compose file:** hardcoded `admin123` / `dev` tokens — replaced by `.env` variables.

---

## 6. Automation

### GitHub Actions

- **Workflow:** `.github/workflows/mlops-data-pipelines.yml`
- **Triggers:** `workflow_dispatch` (booleans per job) + daily cron
- **Scheduled behavior:** daily monitoring; Monday UTC dataset build; optional Sunday Jigsaw ingest behind `MLOPS_ENABLE_SCHEDULED_INGEST`
- **Artifacts:** monitoring JSON/parquet and `quality_report.json` paths when present

### Makefile

- `mlops-install`, `mlops-ingest`, `mlops-synthetic`, `mlops-dataset`, `mlops-monitor`, `mlops-promotion-gate`
- Docker helpers document dependency on `.env`

### Kubernetes

- `infrastructure/kubernetes/mlops-data/pipelines-cronjobs-stub.yaml` — stub `CronJob`s referencing a replaceable image from `Dockerfile.pipelines`
- README updated with pipeline section and MinIO duplication note

### Docker Compose deduplication

- `x-mlops-pipelines-base` YAML anchor — **one** build definition shared by `mlops-pipelines` and `mlops-synthetic` services

---

## 7. `.gitignore` updates

- `!data/README.md` — track the data overview
- `.local/` — default host volumes for MinIO/Jupyter under `./.local/mlops/`

---

## 8. Promotion gate rules (summary)

`python -m data.pipelines.cli_promotion_gate` (or `make mlops-promotion-gate`) reads:

- **Required:** `MLOPS_PROMOTION_QUALITY_REPORT` → `quality_report.json`
- **Optional:** `MLOPS_PROMOTION_MONITOR_JSON` or `MLOPS_PROMOTION_MONITOR_DIR` (latest `monitor_report_*.json`)
- **Optional:** `MLOPS_PROMOTION_MANIFEST` for `build_id` / `dataset_date` in output

**Blocks when:**

1. `quality_report.ok` is false — reason `training_data_quality_failed` or `evaluation_data_too_imbalanced` (from `blocking_codes` / eval minority fraction)
2. Eval minority class fraction < `MLOPS_PROMOTION_EVAL_MINORITY_MIN_FRAC` (default `0.05`) even if quality passed (defense in depth)
3. Monitor report has `any_breach: true` → `live_drift_too_high`
4. If `MLOPS_PROMOTION_REQUIRE_MONITOR=1` and no monitor file → `monitor_report_missing`

Exit code `1` = block, `2` = configuration error.

---

## 9. End-to-end flow (condensed)

1. Ingest external data (Jigsaw) and/or generate synthetic labeled data.
2. Run Mattermost with `mlmoderation` enabled → JSONL logs and feedback.
3. Build dataset → parquet splits + manifest + quality + lineage.
4. Run monitoring → compare live to reference stats.
5. Run promotion gate before deploy/model promotion.

---

## 10. Quick command reference

**Local (repo root):**

```bash
python -m pip install -r data/pipelines/requirements.txt
python -m data.pipelines.cli_jigsaw --source-dir /path/to/csvs   # optional
python -m data.pipelines.cli_synthetic
python -m data.pipelines.cli_dataset_build --strict
python -m data.pipelines.cli_monitoring
export MLOPS_PROMOTION_QUALITY_REPORT=data/artifacts/datasets/<date>/quality_report.json
python -m data.pipelines.cli_promotion_gate --print-json
```

**Compose:**

```bash
cp docker-compose-data.env.example .env   # edit secrets
docker compose -f docker-compose-data.yml up -d minio jupyter
docker compose -f docker-compose-data.yml --profile mlops run --rm mlops-pipelines python -m data.pipelines.cli_monitoring
```

**Team CI:** Actions → **MLOps data pipelines** + repository Variables/Secrets.

**Team K8s:** Build/push `Dockerfile.pipelines`, tune `pipelines-cronjobs-stub.yaml`, apply per `infrastructure/kubernetes/mlops-data/README.md`.

---

## 11. Short README index (per component)

| Component | README |
|-----------|--------|
| Data track overview | `data/README.md` |
| Python pipelines | `data/pipelines/README.md` |
| Go online path | `server/channels/app/mlmoderation/README.md` |
| K8s data namespace | `infrastructure/kubernetes/mlops-data/README.md` |
| This milestone doc | `data/MLOPS_DATA_SUBSYSTEM_MILESTONE.md` (this file) |
| Test checklist | `data/TESTING.md` |

---

## 12. Files created or materially changed (inventory)

**New**

- `docker-compose-data.env.example`
- `data/pipelines/README.md`
- `data/pipelines/promotion_gate.py`, `cli_promotion_gate.py`
- `server/channels/app/mlmoderation/README.md`
- `data/MLOPS_DATA_SUBSYSTEM_MILESTONE.md` (this document)
- `.github/workflows/mlops-data-pipelines.yml` (if not already present in branch)
- `Dockerfile.pipelines`, root `Makefile` (if introduced in same effort)
- `infrastructure/kubernetes/mlops-data/pipelines-cronjobs-stub.yaml` (stub)

**Updated**

- `data/README.md` — reorganized; tracked via `.gitignore` exception
- `data/pipelines/dataset_build.py` — quality v2, lineage, privacy strips, fail-before-export, fairness block, manifest v2
- `data/pipelines/monitoring.py` — promotion hint in report; prior env fixes
- `data/pipelines/cli_dataset_build.py` — `--no-fail-on-quality`, lineage print
- `data/pipelines/__init__.py` — promotion exports
- `docker-compose-data.yml` — anchors, `.env`, local volume defaults, no inline secrets
- `.gitignore` — `!data/README.md`, `.local/`
- `infrastructure/kubernetes/mlops-data/README.md` — CronJob + MinIO dedup note
- `README.md` (root) — link to data docs
- `Makefile` — comments for `.env`
- `Dockerfile.pipelines` — pointer to `data/README.md`

**Go (from integrated inference path; summarized here)**

- `server/channels/app/mlmoderation/*` — features, scores, feedback, service wiring from posts / content flagging

---

*Generated for milestone submission. For day-to-day usage, prefer the shorter [`data/README.md`](README.md).*

