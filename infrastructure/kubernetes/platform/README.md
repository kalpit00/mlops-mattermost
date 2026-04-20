# Platform manifests

Shared **single** object store and MLflow for the project (one VM / one cluster).

| Service | Role |
|---------|------|
| **MinIO** | S3-compatible API at `minio.platform.svc.cluster.local:9000`. **One instance** backs:<br>• `moderation-data` — data pipelines + training inputs (`training/configs/*.yaml` `s3://` URIs) + Mattermost mlmoderation JSONL mirror<br>• `mlflow-artifacts` — MLflow logged files and model artifacts |
| **MLflow** | Tracking + model registry at `mlflow.platform.svc.cluster.local:5000`. Training (`training/train.py`) uses `MLFLOW_TRACKING_URI`; runs log to `--default-artifact-root` `s3://mlflow-artifacts/`. |
| **Ingress** | `platform-ingress.yaml` — browser paths `minio.*` (console :9001) and `mlflow.*` (:5000). |

**Secrets:** `minio-secret` in `platform` (`root-user`, `root-password`). Duplicate the same credentials into namespaces that talk to MinIO from Jobs (`mlops-data`, `mlops-training`, `mattermost`) — Kubernetes does not share Secrets across namespaces.

**Postgres** for Mattermost lives under `mattermost/postgres-*.yaml`; it is unrelated to MLflow’s SQLite metadata on the MLflow PVC.
