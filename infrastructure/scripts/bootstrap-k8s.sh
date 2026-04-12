#!/usr/bin/env bash
set -euo pipefail

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required."
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required."
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required."
  exit 1
fi

echo "[1/4] Installing K3s..."
curl -sfL https://get.k3s.io | sh -

echo "[2/4] Configuring kubeconfig for current user..."
mkdir -p "${HOME}/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "${HOME}/.kube/config"
sudo chown "$(id -u):$(id -g)" "${HOME}/.kube/config"
export KUBECONFIG="${HOME}/.kube/config"

echo "[3/4] Installing ingress-nginx via Helm..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null
helm repo update >/dev/null
kubectl create namespace ingress-nginx --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx

echo "[4/4] Installing metrics-server..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

echo "Bootstrap complete. Verify with:"
echo "  kubectl get nodes"
echo "  kubectl get pods -n ingress-nginx"
echo "  kubectl get pods -n kube-system | rg metrics-server"
