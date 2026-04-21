#!/usr/bin/env bash
set -euo pipefail

# Hardcoded env vars requested by the user.
export MM_DB_USERNAME="mattermost"
export MM_DB_PASSWORD='proj17'
export MM_DB_HOST="mattermost-postgres"
export MM_DB_PORT="5432"
export MM_DB_NAME="mattermost"

export MINIO_ROOT_USER="admin"
export MINIO_ROOT_PASSWORD='proj17platform'

export DATA_JUPYTER_TOKEN='change-me-jupyter-token'

# Public endpoints (from the user)
MINIO_URL_DEFAULT="http://minio.129-114-27-105.nip.io"
BUCKET_DEFAULT="moderation-data"
PREFIX_DEFAULT="mlmoderation/logs"

TIMEOUT_SEC="${TIMEOUT_SEC:-180}"
SLEEP_SEC="${SLEEP_SEC:-10}"
MINIO_URL="${MINIO_URL:-$MINIO_URL_DEFAULT}"
BUCKET="${BUCKET:-$BUCKET_DEFAULT}"
PREFIX="${PREFIX:-$PREFIX_DEFAULT}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_mc() {
  if need_cmd mc; then
    return 0
  fi

  echo "mc (MinIO client) not found; downloading a local copy..."
  local os arch url out
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      echo "Unsupported arch for auto-download: $arch"
      echo "Install mc manually from: https://min.io/docs/minio/linux/reference/minio-mc.html"
      exit 1
      ;;
  esac

  if [[ "$os" != "linux" && "$os" != "darwin" ]]; then
    echo "Unsupported OS for auto-download: $os"
    echo "Install mc manually from: https://min.io/docs/minio/linux/reference/minio-mc.html"
    exit 1
  fi

  url="https://dl.min.io/client/mc/release/${os}-${arch}/mc"
  out="./mc"
  curl -fsSL "$url" -o "$out"
  chmod +x "$out"
  export PATH="$(pwd):$PATH"
}

echo "E2E: verifying MinIO receives Mattermost mlmoderation logs"
echo "- MINIO_URL=$MINIO_URL"
echo "- BUCKET=$BUCKET"
echo "- PREFIX=$PREFIX"
echo "- TIMEOUT_SEC=$TIMEOUT_SEC (poll every ${SLEEP_SEC}s)"
echo

if need_cmd kubectl; then
  echo "Checking required Secret exists (mattermost/minio-secret)..."
  kubectl -n mattermost get secret minio-secret >/dev/null
  echo "OK"
  echo
else
  echo "kubectl not found; skipping in-cluster secret check."
  echo
fi

ensure_mc

mc alias set platform "$MINIO_URL" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null

echo "Waiting for objects under s3://${BUCKET}/${PREFIX}/ (send a Mattermost message during this window)..."

deadline=$(( $(date +%s) + TIMEOUT_SEC ))
while true; do
  # We expect at least one of the online scoring logs to show up.
  if mc ls "platform/${BUCKET}/${PREFIX}/" 2>/dev/null | grep -q "online_scores_v1"; then
    echo "PASS: found online score logs in MinIO."
    echo
    echo "Latest matching objects:"
    mc ls --recursive "platform/${BUCKET}/${PREFIX}/" | grep "online_scores_v1" | tail -n 10 || true
    exit 0
  fi

  now=$(date +%s)
  if (( now >= deadline )); then
    echo "FAIL: timed out waiting for online score logs to appear in MinIO."
    echo
    echo "Debug hints:"
    echo "- Confirm Mattermost is running the fork image (contains mlmoderation hooks)."
    echo "- Confirm JSONL exists in the Mattermost pod: /mattermost/data/mlmoderation/logs"
    echo "- Confirm the sidecar container 'mlmoderation-log-uploader' is running and has MinIO creds."
    exit 1
  fi

  sleep "$SLEEP_SEC"
done

