#!/usr/bin/env bash
# After GitOps deploy (deploy-gitops-stack.sh): run the 4-config training sweep, promote MLflow
# aliases so serving initContainers can download artifacts, then restart serving Deployments.
#
# Requirements: kubectl configured on this machine; repo root as cwd; MinIO seed data
# present for training (see run-config-sweep.sh header).
#
# From the VM / repo root:
#   chmod +x infrastructure/scripts/run-sweep-and-wire-inference.sh
#   ./infrastructure/scripts/run-sweep-and-wire-inference.sh
#
# Skip training if you already ran the sweep and only need aliases + rollout:
#   ./infrastructure/scripts/run-sweep-and-wire-inference.sh --skip-sweep

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

SKIP_SWEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-sweep)
      SKIP_SWEEP=1
      shift
      ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1 (try --skip-sweep)" >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd kubectl

if [[ "${SKIP_SWEEP}" -eq 0 ]]; then
  echo "[1/3] Running 4-config training sweep (sequential Jobs in mlops-training)..."
  bash infrastructure/scripts/run-config-sweep.sh
else
  echo "[1/3] Skipping sweep (--skip-sweep)."
fi

echo "[2/3] Promoting MLflow aliases (staging / canary / production) to latest gate-passed sweep version..."
if ! kubectl -n platform get deploy/mlflow >/dev/null 2>&1; then
  echo "Deployment mlflow not found in namespace platform. Is the platform stack synced?" >&2
  exit 1
fi

kubectl -n platform exec -i deploy/mlflow -- \
  env MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  python3 - < infrastructure/scripts/promote_mlflow_aliases.py

echo "[3/3] Restarting serving Deployments so fetch-model initContainers run again..."
SERVING_NS=(mlops-staging mlops-canary mlops-serving)
for ns in "${SERVING_NS[@]}"; do
  if kubectl get deploy ml-serving -n "${ns}" >/dev/null 2>&1; then
    kubectl rollout restart deployment/ml-serving -n "${ns}"
    kubectl rollout status deployment/ml-serving -n "${ns}" --timeout=600s
    echo "    rollout ok: ${ns}/ml-serving"
  else
    echo "    (skip) no Deployment ml-serving in namespace ${ns}"
  fi
done

echo
echo "Smoke-check production serving /health (inside mlops-serving pod)..."
if kubectl get deploy ml-serving -n mlops-serving >/dev/null 2>&1; then
  kubectl -n mlops-serving exec deploy/ml-serving -c api -- \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10).read()" \
    && echo "    /health OK"
else
  echo "    (skip) ml-serving not in mlops-serving"
fi

echo
echo "Done. Inference should now resolve MLflow aliases and load /models/tfidf_logreg_pipeline.joblib."
