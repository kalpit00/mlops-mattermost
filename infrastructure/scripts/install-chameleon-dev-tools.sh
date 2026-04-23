#!/usr/bin/env bash
# One-time package install on a fresh Chameleon CC-Ubuntu VM for this repo's bring-up path.
# Run: sudo ./infrastructure/scripts/install-chameleon-dev-tools.sh
#
# Installs: git, Docker (image builds), curl, perl (set-floating-ip-in-manifests.sh), jq (optional ops).
# Does NOT install: npm, node, uv — not required on the VM if you only use Dockerfiles
# (build-mlops-images.sh builds inside Docker). Add them yourself for local non-Docker builds.
#
# After this script: add your user to the docker group (script does), then log out and SSH back in
# so `docker` works without sudo, OR use `sudo docker` for builds.

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  docker.io \
  perl \
  jq \
  ripgrep

# Allow the default Chameleon user to run docker without sudo
if [[ -n "${SUDO_USER:-}" ]] && id "$SUDO_USER" &>/dev/null; then
  usermod -aG docker "$SUDO_USER"
  echo "Added $SUDO_USER to the docker group. Log out and SSH back in (or newgrp docker) for it to take effect."
fi

systemctl enable --now docker 2>/dev/null || true

echo "Done. Optional: install MinIO client (mc) for host-side debugging — e.g."
echo "  curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc"
echo "Next: from repo, ./infrastructure/scripts/bootstrap-k8s.sh"
