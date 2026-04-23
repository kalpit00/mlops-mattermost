#!/usr/bin/env bash
# Build all project-built images with the tags used in k8s/*.yaml (see docs/DOCKER-BUILDS.md).
# Run on the Chameleon VM from the repository root, or use DOCKER_DEFAULT_PLATFORM=linux/amd64 when building on Apple Silicon.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"

echo "==> mattermost-mlops:local (webapp with moderation UI + server)"
docker build -f server/build/Dockerfile.mlops -t mattermost-mlops:local .

echo "==> mlops-serving:local (FastAPI /score + /health)"
docker build -f Dockerfile.serving -t mlops-serving:local .

echo "==> mlops-training:local (training.train)"
docker build -f Dockerfile.training -t mlops-training:local .

if [[ -d data/pipelines ]] && [[ -f data/pipelines/requirements.txt ]]; then
  echo "==> mlops-pipelines:local (data.pipelines CLIs for CronJobs)"
  docker build -f Dockerfile.pipelines -t mlops-pipelines:local .
else
  echo "==> skip mlops-pipelines (data/pipelines not present; optional for Jupyter + CronJobs)"
fi

echo "Done. Load into K3s: docker save ... | sudo k3s ctr images import -"
echo "Reference: infrastructure/docs/DOCKER-BUILDS.md"
