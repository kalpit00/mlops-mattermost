#!/usr/bin/env bash
set -euo pipefail

# Avoid indefinite hangs if the API server is slow (default kubectl wait can feel "stuck").
kubectl() { command kubectl --request-timeout=120s "$@"; }

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
# batch/v1 Job spec.template is immutable; delete so apply can replace when the manifest changes.
kubectl delete job ml-training -n mlops-training --ignore-not-found
kubectl apply -f "${K8S_DIR}/team-stubs"

echo "[7/8] Applying training CronJobs (optional; requires training image + mlops-training/minio-secret)..."
if [[ -d "${K8S_DIR}/mlops-training" ]]; then
  kubectl apply -f "${K8S_DIR}/mlops-training"
fi

echo "[8/8] Cluster status (listing all namespaces may take a few seconds)..."
kubectl get pods -A
kubectl get pvc -A
kubectl get ingress -A

echo "Deployment sequence complete."
