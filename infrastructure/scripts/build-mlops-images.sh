#!/usr/bin/env bash
# Build all project-built images with the tags used in k8s/*.yaml (see docs/DOCKER-BUILDS.md).
# Run on the Chameleon VM from the repository root, or use DOCKER_DEFAULT_PLATFORM=linux/amd64 when building on Apple Silicon.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"

echo "==> mattermost-mlops:v5 (webapp with moderation UI + server metrics)"
docker build -f server/build/Dockerfile.mlops -t kalpit00/mattermost-mlops:v5 .

echo "==> mlops-serving:v3 (FastAPI /score + /health + /metrics)"
docker build -f Dockerfile.serving -t kalpit00/mlops-serving:v3 .

echo "==> mlops-training:local (training.train)"
docker build -f Dockerfile.training -t mlops-training:local .

if [[ -d mlops_data/pipelines ]] && [[ -f mlops_data/pipelines/requirements.txt ]]; then
  echo "==> mlops-pipelines:v1 (mlops_data.pipelines CLIs for CronJobs + Pushgateway)"
  docker build -f Dockerfile.pipelines -t kalpit00/mlops-pipelines:v1 .
else
  echo "==> skip mlops-pipelines (mlops_data/pipelines not present; optional for Jupyter + CronJobs)"
fi

echo "Done. Load into K3s: docker save ... | sudo k3s ctr images import -"
echo "Reference: infrastructure/docs/DOCKER-BUILDS.md"
