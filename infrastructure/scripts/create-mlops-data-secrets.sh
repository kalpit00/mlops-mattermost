#!/usr/bin/env bash
set -euo pipefail

# Secrets for namespace mlops-data (Jupyter + pipeline CronJobs).
# Object storage is the single cluster MinIO in `platform` — use the SAME credentials as
# `kubectl -n platform create secret minio-secret ...` (see create-secrets.sh).
# Do not commit real values. Example:
#   export MINIO_ROOT_USER=...
#   export MINIO_ROOT_PASSWORD=...
#   export DATA_JUPYTER_TOKEN=...
#   ./create-mlops-data-secrets.sh

required_vars=(
  MINIO_ROOT_USER
  MINIO_ROOT_PASSWORD
  DATA_JUPYTER_TOKEN
)

for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: ${v}"
    exit 1
  fi
done

kubectl create namespace mlops-data --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic minio-secret \
  --from-literal=root-user="${MINIO_ROOT_USER}" \
  --from-literal=root-password="${MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic data-jupyter-secret \
  --from-literal=token="${DATA_JUPYTER_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "mlops-data secrets created/updated (minio-secret mirrors platform MinIO credentials)."
