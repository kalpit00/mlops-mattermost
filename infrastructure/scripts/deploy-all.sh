#!/usr/bin/env bash
# Apply all Kubernetes workloads (requires secrets: create-secrets.sh + create-mlops-data-secrets.sh).
# Build images first: infrastructure/scripts/build-mlops-images.sh — see infrastructure/docs/DOCKER-BUILDS.md
set -euo pipefail

# Avoid indefinite hangs if the API server is slow (default kubectl wait can feel "stuck").
kubectl() { command kubectl --request-timeout=120s "$@"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_DIR="${INFRA_DIR}/k8s"

echo "[1/7] Applying namespaces..."
kubectl apply -f "${K8S_DIR}/namespaces"

echo "[2/7] Applying storage manifests..."
kubectl apply -f "${K8S_DIR}/storage"

# App Ingresses live in mattermost/, platform/, mlops-data/ (k8s/ingress/ is reserved; may be empty).

echo "[preflight] Checking required secrets (run create-secrets.sh + create-mlops-data-secrets.sh)..."
kubectl -n mattermost get secret mattermost-db-secret >/dev/null
kubectl -n mattermost get secret mattermost-app-secret >/dev/null
kubectl -n mattermost get secret minio-secret >/dev/null
kubectl -n platform get secret minio-secret >/dev/null
kubectl -n mlops-training get secret minio-secret >/dev/null
kubectl -n mlops-serving get secret minio-secret >/dev/null
kubectl -n mlops-data get secret minio-secret >/dev/null
kubectl -n mlops-data get secret data-jupyter-secret >/dev/null

echo "[3/7] Deploying Mattermost stack..."
kubectl apply -f "${K8S_DIR}/mattermost"

echo "[4/7] Deploying shared platform stack..."
kubectl apply -f "${K8S_DIR}/platform"

echo "[5/7] Applying app workloads (serving + one-shot training Job + training CronJob)..."
# batch/v1 Job spec.template is immutable; delete so apply can replace when the manifest changes.
kubectl delete job ml-training -n mlops-training --ignore-not-found
kubectl apply -f "${K8S_DIR}/apps/serving"
kubectl apply -f "${K8S_DIR}/apps/training"

echo "[6/7] Deploying mlops-data (Jupyter, ingress, optional pipeline CronJobs)..."
kubectl apply -f "${K8S_DIR}/mlops-data"

echo "[7/7] Cluster status (listing all namespaces may take a few seconds)..."
kubectl get pods -A
kubectl get pvc -A
kubectl get ingress -A

echo "Deployment sequence complete."
