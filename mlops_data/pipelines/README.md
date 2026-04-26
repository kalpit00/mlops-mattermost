# `mlops_data/pipelines` — batch MLOps jobs

Python 3.11+. Install: `pip install -r mlops_data/pipelines/requirements.txt`. Run CLIs from the **repository root** so `python -m mlops_data.pipelines.*` resolves.

**Data quality checkpoints (minimal):** evaluated at **ingestion** (`cli_jigsaw`), **retraining dataset build** (`cli_dataset_build`), and **production/live inference drift** (`cli_monitoring`).

| Module | CLI | Purpose |
|--------|-----|---------|
| [`jigsaw_ingestion.py`](jigsaw_ingestion.py) | `python -m mlops_data.pipelines.cli_jigsaw` | External CSV → binary parquet + manifest; optional S3/MinIO. |
| [`synthetic_messages.py`](synthetic_messages.py) | `python -m mlops_data.pipelines.cli_synthetic` | Synthetic Post-shaped data; artifact and/or HTTP to Mattermost. |
| [`dataset_build.py`](dataset_build.py) | `python -m mlops_data.pipelines.cli_dataset_build` | Train/val/eval parquet + `manifest.json` + `quality_report.json` + `training_lineage.json`. |
| [`monitoring.py`](monitoring.py) | `python -m mlops_data.pipelines.cli_monitoring` | Ingestion / training / live drift JSON (+ optional parquet summary). |
| [`promotion_gate.py`](promotion_gate.py) | `python -m mlops_data.pipelines.cli_promotion_gate` | Exit non-zero to block deploy when quality, eval balance, or drift fail. |

**Config:** each module uses `MLOPS_*` environment variables (see `from_env` in the module). **Secrets** belong in `.env`, shell, or CI Secrets — never in repo files.

**Docker image:** repo root `Dockerfile.pipelines` copies this tree for CI/Kubernetes/Compose.
