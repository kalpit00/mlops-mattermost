#!/usr/bin/env bash
set -euo pipefail

kubectl() { command kubectl --request-timeout=120s "$@"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_DIR="${INFRA_DIR}/kubernetes/mlops-data"

echo "[1/3] Namespace..."
kubectl apply -f "${INFRA_DIR}/kubernetes/namespaces/mlops-data.yaml"

echo "[2/3] Preflight: secrets (minio-secret must match platform MinIO credentials)..."
kubectl -n mlops-data get secret minio-secret >/dev/null
kubectl -n mlops-data get secret data-jupyter-secret >/dev/null

echo "[3/3] Jupyter + ingress + optional CronJobs..."
kubectl apply -f "${K8S_DIR}/jupyter-pvc.yaml"
kubectl apply -f "${K8S_DIR}/jupyter-deployment.yaml"
kubectl apply -f "${K8S_DIR}/jupyter-service.yaml"
kubectl apply -f "${K8S_DIR}/mlops-data-ingress.yaml"

echo "Optional CronJobs (often suspended until pipeline image is pushed)..."
kubectl apply -f "${K8S_DIR}/pipelines-cronjobs.yaml"

kubectl get pods,svc,ingress -n mlops-data
echo "mlops-data deploy complete (single MinIO lives in namespace platform)."
