#!/usr/bin/env bash
set -euo pipefail

# Clean GitOps bring-up for the VM after images are already built/pushed.
# Run from the repository root:
#   bash infrastructure/scripts/deploy-gitops-stack.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f infrastructure/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source infrastructure/.env
  set +a
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

sync_app() {
  local app="$1"
  kubectl -n argocd patch application "${app}" \
    --type merge \
    -p '{"operation":{"sync":{"revision":"master","prune":true}}}' >/dev/null || true
}

require_cmd kubectl
require_cmd helm

echo "[1/8] Creating Kubernetes secrets from infrastructure/.env..."
./infrastructure/scripts/create-secrets.sh
./infrastructure/scripts/create-mlops-data-secrets.sh

echo "[2/8] Updating Helm chart dependencies..."
helm dependency update infrastructure/helm/observability-stack

echo "[3/8] Installing Prometheus Operator CRDs with server-side apply..."
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT
tar xzf infrastructure/helm/observability-stack/charts/kube-prometheus-stack-*.tgz -C "${tmp_dir}"
kubectl apply --server-side --force-conflicts \
  -f "${tmp_dir}/kube-prometheus-stack/charts/crds/crds/"

echo "[4/8] Installing or updating ArgoCD..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.0/manifests/install.yaml
kubectl -n argocd wait --for=condition=available deployment/argocd-server --timeout=300s

echo "[5/8] Applying ArgoCD project, applications, and public ArgoCD ingress..."
kubectl apply -f infrastructure/argocd/projects/mlops.yaml
kubectl apply -f infrastructure/argocd/applications/mlops-applications.yaml
kubectl apply -f infrastructure/argocd/bootstrap/argocd-ingress.yaml

echo "[6/8] Triggering manual-sync applications..."
sync_app mlops-production
sync_app mlops-canary
sync_app mlops-observability

echo "[7/8] Waiting for key workloads. Some pods can take a few minutes on a cold VM..."
kubectl -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy application/mlops-platform --timeout=600s || true
kubectl -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy application/mlops-staging --timeout=600s || true
kubectl -n mattermost rollout status deploy/mattermost --timeout=600s || true
kubectl -n observability rollout status deploy/kube-prometheus-stack-operator --timeout=600s || true
kubectl -n observability rollout restart deploy/kube-prometheus-stack-operator >/dev/null 2>&1 || true
kubectl -n observability rollout status deploy/kube-prometheus-stack-operator --timeout=600s || true

echo "[8/8] Current status and public demo URLs..."
kubectl get application -n argocd
kubectl get ingress -A

cat <<'EOF'

Public demo URLs:
  Mattermost:    http://129-114-27-105.nip.io
  MLflow:        http://mlflow.129-114-27-105.nip.io
  MinIO:         http://minio.129-114-27-105.nip.io
  Jupyter:       http://data-jupyter.129-114-27-105.nip.io
  Grafana:       http://grafana.129-114-27-105.nip.io
  Prometheus:    http://prometheus.129-114-27-105.nip.io
  Alertmanager:  http://alertmanager.129-114-27-105.nip.io
  Loki ready:    http://loki.129-114-27-105.nip.io/ready
  Pushgateway:   http://pushgateway.129-114-27-105.nip.io
  ArgoCD:        http://argocd.129-114-27-105.nip.io

ArgoCD username is admin. To print its password:
  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
EOF
