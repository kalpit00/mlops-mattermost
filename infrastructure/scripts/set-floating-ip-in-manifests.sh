#!/usr/bin/env bash
# Replace Chameleon floating IP in Kubernetes Ingress URLs (nip.io hostname encoding).
#
# Usage (from repo root, after you know the new public IP):
#   ./infrastructure/scripts/set-floating-ip-in-manifests.sh NEW_FLOAT_IP [OLD_FLOAT_IP]
#
# Defaults OLD_FLOAT_IP to 129.114.25.58 if omitted.
# nip.io label: dots -> hyphens (e.g. 203.0.113.10 -> 203-0-113-10.nip.io)
#
# Then: git diff, commit, deploy-all.sh on the VM, kubectl apply refreshed manifests.

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 NEW_FLOAT_IP [OLD_FLOAT_IP]" >&2
  exit 1
fi

NEW_DOTTED="$1"
OLD_DOTTED="${2:-129.114.25.58}"

if ! [[ "$NEW_DOTTED" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: NEW_FLOAT_IP must look like 203.0.113.10" >&2
  exit 1
fi

NEW_NIP="${NEW_DOTTED//./-}"
OLD_NIP="${OLD_DOTTED//./-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

FILES=(
  infrastructure/kubernetes/mattermost/mattermost-ingress.yaml
  infrastructure/kubernetes/mattermost/mattermost-deployment.yaml
  infrastructure/kubernetes/mattermost/README.md
  infrastructure/kubernetes/platform/platform-ingress.yaml
  infrastructure/kubernetes/mlops-data/mlops-data-ingress.yaml
  infrastructure/kubernetes/mlops-data/README.md
)

for f in "${FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing file: $f" >&2
    exit 1
  fi
done

echo "Replacing nip label $OLD_NIP -> $NEW_NIP and dotted $OLD_DOTTED -> $NEW_DOTTED"
for f in "${FILES[@]}"; do
  perl -i -pe "s/\Q$OLD_NIP\E/$NEW_NIP/g; s/\Q$OLD_DOTTED\E/$NEW_DOTTED/g" "$f"
  echo "  updated $f"
done

echo "Done. Review: git diff -- ${FILES[*]}"
