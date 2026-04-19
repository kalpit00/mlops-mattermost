# mlops-data — Data team workloads (from `docker-compose-data.yml`)

Kubernetes equivalents of the data member’s Compose stack: **MinIO** and **Jupyter**.

These are **not** applied by `scripts/deploy-all.sh` (platform `MinIO` already lives in `namespace: platform`). Apply here only when the team wants a **separate** data-plane MinIO + notebook in `mlops-data`.

## Secrets (create before apply; do not commit values)

```bash
kubectl create namespace mlops-data --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic data-minio-secret \
  --from-literal=root-user='REPLACE_ME' \
  --from-literal=root-password='REPLACE_ME' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic data-jupyter-secret \
  --from-literal=token='REPLACE_ME' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Apply order

```bash
kubectl apply -f minio-pvc.yaml -f jupyter-pvc.yaml
kubectl apply -f minio-deployment.yaml -f minio-service.yaml
kubectl apply -f jupyter-deployment.yaml -f jupyter-service.yaml
```

Source Compose file (reference): `docker-compose-data.yml` at repo root.

## Pipeline CronJobs (optional)

[`pipelines-cronjobs-stub.yaml`](pipelines-cronjobs-stub.yaml) defines **stub** `CronJob` resources (drift monitor + weekly dataset build). Build and push an image from the repo root `Dockerfile.pipelines`, replace `ghcr.io/example/mlops-pipelines:latest`, add PVC/volume mounts if the job needs a checkout or shared artifact tree. This is **separate** from MinIO/Jupyter — apply only when the team schedules batch jobs in `mlops-data`.

**Note:** `infrastructure/kubernetes/platform/` may already define MinIO for the platform namespace. Use either platform MinIO or this namespace’s MinIO — not two production writes to different buckets without coordination.
