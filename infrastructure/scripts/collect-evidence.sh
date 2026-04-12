#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-./evidence}"
mkdir -p "${OUT_DIR}"

echo "[1/6] Capturing cluster overview..."
kubectl get nodes -o wide > "${OUT_DIR}/nodes.txt"
kubectl get pods -A -o wide > "${OUT_DIR}/pods-all.txt"
kubectl get svc -A > "${OUT_DIR}/services-all.txt"
kubectl get ingress -A > "${OUT_DIR}/ingress-all.txt"
kubectl get pvc -A > "${OUT_DIR}/pvc-all.txt"

echo "[2/6] Capturing node and pod metrics (requires metrics-server)..."
kubectl top nodes > "${OUT_DIR}/top-nodes.txt"
kubectl top pods -A > "${OUT_DIR}/top-pods-all.txt"

echo "[3/6] Capturing mattermost namespace details..."
kubectl get all -n mattermost > "${OUT_DIR}/mattermost-all.txt"
kubectl describe pods -n mattermost > "${OUT_DIR}/mattermost-pods-describe.txt"

echo "[4/6] Capturing platform namespace details..."
kubectl get all -n platform > "${OUT_DIR}/platform-all.txt"
kubectl describe pods -n platform > "${OUT_DIR}/platform-pods-describe.txt"

echo "[5/6] Capturing resource specs from manifests..."
kubectl get deploy,statefulset,cronjob -A -o yaml > "${OUT_DIR}/workload-specs.yaml"

echo "[6/6] Done. Add screenshots separately for browser and top output."
echo "Evidence written to: ${OUT_DIR}"
