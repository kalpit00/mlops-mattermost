#!/usr/bin/env bash
set -euo pipefail

# Creates secrets for namespace mlops-data (docker-compose-data.yml parity).
# Do not commit real values. Example:
#   export DATA_MINIO_ROOT_USER=...
#   export DATA_MINIO_ROOT_PASSWORD=...
#   export DATA_JUPYTER_TOKEN=...
#   ./create-mlops-data-secrets.sh

required_vars=(
  DATA_MINIO_ROOT_USER
  DATA_MINIO_ROOT_PASSWORD
  DATA_JUPYTER_TOKEN
)

for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: ${v}"
    exit 1
  fi
done

kubectl create namespace mlops-data --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic data-minio-secret \
  --from-literal=root-user="${DATA_MINIO_ROOT_USER}" \
  --from-literal=root-password="${DATA_MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-data create secret generic data-jupyter-secret \
  --from-literal=token="${DATA_JUPYTER_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "mlops-data secrets created/updated."
