#!/usr/bin/env bash
set -euo pipefail
# Expected env vars: see infrastructure/secrets.env.example (copy to infrastructure/secrets.env, then: source that file)

required_vars=(
  MM_DB_USERNAME
  MM_DB_PASSWORD
  MM_DB_HOST
  MM_DB_PORT
  MM_DB_NAME
  MINIO_ROOT_USER
  MINIO_ROOT_PASSWORD
)

for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: ${v}"
    exit 1
  fi
done

mm_datasource="postgres://${MM_DB_USERNAME}:${MM_DB_PASSWORD}@${MM_DB_HOST}:${MM_DB_PORT}/${MM_DB_NAME}?sslmode=disable&connect_timeout=10"

kubectl create namespace mattermost --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace mlops-training --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace mlops-serving --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mattermost create secret generic mattermost-db-secret \
  --from-literal=username="${MM_DB_USERNAME}" \
  --from-literal=password="${MM_DB_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mattermost create secret generic mattermost-app-secret \
  --from-literal=datasource="${mm_datasource}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n platform create secret generic minio-secret \
  --from-literal=root-user="${MINIO_ROOT_USER}" \
  --from-literal=root-password="${MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mattermost create secret generic minio-secret \
  --from-literal=root-user="${MINIO_ROOT_USER}" \
  --from-literal=root-password="${MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Team workloads (training jobs + serving initContainer) also need MinIO credentials, but Secrets are namespace-scoped.
kubectl -n mlops-training create secret generic minio-secret \
  --from-literal=root-user="${MINIO_ROOT_USER}" \
  --from-literal=root-password="${MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mlops-serving create secret generic minio-secret \
  --from-literal=root-user="${MINIO_ROOT_USER}" \
  --from-literal=root-password="${MINIO_ROOT_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secrets created/updated successfully."
