#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_DIR="${INFRA_DIR}/kubernetes"

echo "[1/7] Applying namespaces..."
kubectl apply -f "${K8S_DIR}/namespaces"

echo "[2/7] Applying storage manifests..."
kubectl apply -f "${K8S_DIR}/storage"

echo "[3/7] Applying ingress manifests..."
kubectl apply -f "${K8S_DIR}/ingress"

echo "[preflight] Checking required secrets..."
kubectl -n mattermost get secret mattermost-db-secret >/dev/null
kubectl -n mattermost get secret mattermost-app-secret >/dev/null
kubectl -n platform get secret minio-secret >/dev/null

echo "[4/7] Deploying Mattermost stack..."
kubectl apply -f "${K8S_DIR}/mattermost"

echo "[5/7] Deploying shared platform stack..."
kubectl apply -f "${K8S_DIR}/platform"

echo "[6/7] Applying team stubs..."
kubectl apply -f "${K8S_DIR}/team-stubs"

echo "[7/7] Current rollout status (manual follow-up may still be needed):"
kubectl get pods -A
kubectl get pvc -A
kubectl get ingress -A

echo "Deployment sequence complete."
