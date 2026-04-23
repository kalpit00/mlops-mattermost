# mlops-data — Data team stack (from `docker-compose-data.yml`)

Kubernetes: **Jupyter** plus optional **`mlops-pipelines` CronJobs**. Object storage is **not** deployed here — use the **single MinIO** in namespace `platform` (same as Mattermost log upload, MLflow artifacts, and training data in `s3://moderation-data`).

## What the data member owns (reference)

| Artifact                                     | Role                                                                          |
| -------------------------------------------- | ----------------------------------------------------------------------------- |
| `docker-compose-data.yml`                    | Local dev: MinIO + Jupyter + `mlops-pipelines` profiles                       |
| `Dockerfile.pipelines`                       | Image for `python -m data.pipelines.*`                                        |
| `.github/workflows/mlops-data-pipelines.yml` | CI schedules / manual runs                                                    |
| `data/pipelines/`                            | Pipeline code uploaded to S3 bucket **`moderation-data`** on the shared MinIO |

Ensure `data/pipelines/` is committed (see root `.gitignore` allowlist) so `Dockerfile.pipelines` builds in CI and locally.

## URLs (same floating IP as the rest of the stack; nip.io)

| Service                              | URL                                                       |
| ------------------------------------ | --------------------------------------------------------- |
| Data Jupyter                         | `http://data-jupyter.129-114-27-105.nip.io`               |
| **MinIO console (shared)**           | `http://minio.129-114-27-105.nip.io` (`platform` Ingress) |
| **MLflow (training metrics/models)** | `http://mlflow.129-114-27-105.nip.io`                     |

Log in to Jupyter with the token you set in `DATA_JUPYTER_TOKEN`.

## Deploy (default path)

Jupyter and these manifests are applied by **`infrastructure/scripts/deploy-all.sh`** in step **6/7**, **after** `create-mlops-data-secrets.sh` (with `DATA_JUPYTER_TOKEN` in `infrastructure/.env`). The `minio-secret` in `mlops-data` must match **`kubectl -n platform get secret minio-secret`** (one MinIO server).

**Re-apply this folder only:** `infrastructure/scripts/deploy-mlops-data.sh` (from repo root).

**Manual / CI without full stack** (from repo root, with `kubectl` configured):

```bash
set -a && source infrastructure/.env && set +a
./infrastructure/scripts/create-mlops-data-secrets.sh
./infrastructure/scripts/deploy-mlops-data.sh
```

## Manual apply order

```bash
kubectl apply -f ../namespaces/mlops-data.yaml
# secrets: use create-mlops-data-secrets.sh
kubectl apply -f jupyter-pvc.yaml
kubectl apply -f jupyter-deployment.yaml -f jupyter-service.yaml
kubectl apply -f mlops-data-ingress.yaml
kubectl apply -f pipelines-cronjobs.yaml
```

## Pipeline CronJobs

[`pipelines-cronjobs.yaml`](pipelines-cronjobs.yaml) runs the same modules as Compose / GitHub Actions (`data.pipelines.cli_monitoring`, `data.pipelines.cli_dataset_build`). They:

- Use **`MLOPS_S3_ENDPOINT=http://minio.platform.svc.cluster.local:9000`** and **`MLOPS_S3_BUCKET=moderation-data`**.
- Read credentials from **`minio-secret`** in namespace `mlops-data` (must match the platform MinIO credentials).
- Start with **`suspend: true`** so a missing image does not spam failures. Build/push from `Dockerfile.pipelines`, edit the `image:` field, then set **`suspend: false`** when ready.

Optional monitoring paths (`MLOPS_MONITOR_*`) can be extended later via ConfigMap or extra env on the CronJob.

## Migrating from the old `data-minio` Deployment

If you previously applied `minio-deployment.yaml` in `mlops-data`, delete the duplicate and its PVC only **after** copying any needed objects to the `platform` MinIO bucket `moderation-data` (or re-run pipelines):

```bash
kubectl delete deployment,svc data-minio -n mlops-data --ignore-not-found
kubectl delete pvc data-minio-pvc -n mlops-data --ignore-not-found
kubectl -n mlops-data delete secret data-minio-secret --ignore-not-found
```

Recreate `minio-secret` in `mlops-data` with `create-mlops-data-secrets.sh` (credentials matching `platform`).
