# mlops-data — Data team stack (from `docker-compose-data.yml`)

Kubernetes equivalent of the Compose services **`minio`**, **`jupyter`**, and optional **`mlops-pipelines`** CronJobs.

This namespace is **separate** from `platform` (which already runs MinIO + MLflow for the shared MLOps demo). Use **either** coordination with platform or this data-plane MinIO only—avoid writing the same logical datasets to two uncoordinated buckets without a plan.

## What the data member added (reference)

| Artifact | Role |
|----------|------|
| `docker-compose-data.yml` | MinIO + Jupyter + `mlops-pipelines` / `mlops-synthetic` profiles |
| `Dockerfile.pipelines` | Image for `python -m data.pipelines.*` (expects `data/pipelines` in Git and copied into the image) |
| `.github/workflows/mlops-data-pipelines.yml` | CI schedules / manual runs (mirrors some of the CronJob CLIs) |
| `server/channels/app/mlmoderation/` | Server-side hooks / logging related to moderation (not deployed by this folder) |

Ensure `data/pipelines/` is committed (see root `.gitignore` allowlist) so `Dockerfile.pipelines` builds in CI and locally.

## URLs (same floating IP as the rest of the stack; nip.io)

After you apply `mlops-data-ingress.yaml`, open (update host if your FIP changes):

| Service | URL |
|---------|-----|
| Data Jupyter | `http://data-jupyter.129-114-25-58.nip.io` |
| Data MinIO console | `http://data-minio.129-114-25-58.nip.io` |

Log in to Jupyter with the token you set in `DATA_JUPYTER_TOKEN`.

## One-command path on the cluster node

From `infrastructure/scripts/` (after `bootstrap-k8s.sh`):

```bash
export DATA_MINIO_ROOT_USER='...'
export DATA_MINIO_ROOT_PASSWORD='...'
export DATA_JUPYTER_TOKEN='...'
chmod +x create-mlops-data-secrets.sh deploy-mlops-data.sh
./create-mlops-data-secrets.sh
./deploy-mlops-data.sh
```

## Manual apply order (same as the script)

```bash
kubectl apply -f ../kubernetes/namespaces/mlops-data.yaml
# secrets: use create-mlops-data-secrets.sh
kubectl apply -f minio-pvc.yaml -f jupyter-pvc.yaml
kubectl apply -f minio-deployment.yaml -f minio-service.yaml
kubectl apply -f jupyter-deployment.yaml -f jupyter-service.yaml
kubectl apply -f mlops-data-ingress.yaml
kubectl apply -f pipelines-cronjobs.yaml
```

## Pipeline CronJobs

[`pipelines-cronjobs.yaml`](pipelines-cronjobs.yaml) runs the same modules as Compose / GitHub Actions (`data.pipelines.cli_monitoring`, `data.pipelines.cli_dataset_build`). They:

- Point **`MLOPS_S3_*`** at the in-cluster **`data-minio`** Service.
- Start with **`suspend: true`** so a missing image does not spam failures. Build/push from `Dockerfile.pipelines`, edit the `image:` field, then set **`suspend: false`** when ready.

Optional monitoring paths (`MLOPS_MONITOR_*`) can be extended later via ConfigMap or extra env on the CronJob.
