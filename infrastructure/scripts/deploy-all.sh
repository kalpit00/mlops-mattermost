#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_DIR="${INFRA_DIR}/kubernetes"

echo "[1/8] Applying namespaces..."
kubectl apply -f "${K8S_DIR}/namespaces"

echo "[2/8] Applying storage manifests..."
kubectl apply -f "${K8S_DIR}/storage"

echo "[3/8] Applying ingress manifests..."
kubectl apply -f "${K8S_DIR}/ingress"

echo "[preflight] Checking required secrets..."
kubectl -n mattermost get secret mattermost-db-secret >/dev/null
kubectl -n mattermost get secret mattermost-app-secret >/dev/null
kubectl -n mattermost get secret minio-secret >/dev/null
kubectl -n platform get secret minio-secret >/dev/null
kubectl -n mlops-training get secret minio-secret >/dev/null
kubectl -n mlops-serving get secret minio-secret >/dev/null

echo "[4/8] Deploying Mattermost stack..."
kubectl apply -f "${K8S_DIR}/mattermost"

echo "[5/8] Deploying shared platform stack..."
kubectl apply -f "${K8S_DIR}/platform"

echo "[6/8] Applying team stubs..."
kubectl apply -f "${K8S_DIR}/team-stubs"

echo "[7/8] Applying training CronJobs (optional; requires training image + mlops-training/minio-secret)..."
if [[ -d "${K8S_DIR}/mlops-training" ]]; then
  kubectl apply -f "${K8S_DIR}/mlops-training"
fi

echo "[8/8] Current rollout status (manual follow-up may still be needed):"
kubectl get pods -A
kubectl get pvc -A
kubectl get ingress -A

echo "Deployment sequence complete."
