#!/usr/bin/env bash
# Install K3s, ingress-nginx, metrics-server.
# Requires: curl. kubectl is provided by K3s; Helm is installed if missing.
# On a fresh VM run install-chameleon-dev-tools.sh (Docker, git, …) first, then this script.
set -euo pipefail

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required. On Ubuntu: sudo apt-get install -y curl"
  exit 1
fi

if ! systemctl is-active --quiet k3s 2>/dev/null; then
  echo "[1/4] Installing K3s..."
  curl -sfL https://get.k3s.io | sh -
else
  echo "[1/4] K3s already active; skipping get.k3s.io install."
fi

if [[ ! -f /etc/rancher/k3s/k3s.yaml ]]; then
  echo "K3s kubeconfig missing at /etc/rancher/k3s/k3s.yaml. Check: sudo systemctl status k3s" >&2
  exit 1
fi

echo "[2/4] Configuring kubeconfig for current user..."
mkdir -p "${HOME}/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "${HOME}/.kube/config"
sudo chown "$(id -u):$(id -g)" "${HOME}/.kube/config"
export KUBECONFIG="${HOME}/.kube/config"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not on PATH after K3s. Try: export PATH=\"/usr/local/bin:\$PATH\" (or use: sudo k3s kubectl ...)" >&2
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "Installing Helm 3 (required for ingress-nginx)..."
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi
if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found after install. Ensure /usr/local/bin is on PATH." >&2
  exit 1
fi

echo "[3/4] Installing ingress-nginx via Helm..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update >/dev/null
kubectl create namespace ingress-nginx --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx

echo "[4/4] Installing metrics-server..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

echo "Bootstrap complete. Verify with:"
echo "  export KUBECONFIG=\"\${HOME}/.kube/config\""
echo "  kubectl get nodes"
echo "  kubectl get pods -n ingress-nginx"
echo "  kubectl get pods -n kube-system | grep metrics-server || true"
