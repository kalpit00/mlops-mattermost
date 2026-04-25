#!/usr/bin/env bash
# Sequentially train all 4 sweep configs (small, baseline, bigram, balanced)
# and register each as a new version of `tfidf_logreg` in MLflow.
#
# Why sequential and not parallel: this single-node K3s also hosts Mattermost,
# Postgres, MLflow, MinIO, and the serving Deployment. Running four 4Gi /
# 2-CPU training Jobs in parallel risks tipping the node into memory pressure
# and evicting unrelated workloads. Sequential trades a few minutes of latency
# for a calm cluster.
#
# Run from the repository root on the VM:
#   ./infrastructure/scripts/run-config-sweep.sh
#
# After completion: open MLflow UI, compare the 4 runs in the `moderation`
# experiment, pick a winner, then proceed to Phase B.

set -euo pipefail

NS="mlops-training"
SWEEP_DIR="infrastructure/k8s/apps/training/sweep"
CONFIGS=(small baseline bigram balanced)

# Per-job wait timeout. TF-IDF + LogReg on Jigsaw fits in a few minutes; 30m
# is generous and only matters if the cluster is under heavy load.
WAIT_TIMEOUT="30m"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()  { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
err() { printf '    \033[1;31m✗\033[0m %s\n' "$*" >&2; }

#------------------------------------------------------------------------------
# Pre-flight
#------------------------------------------------------------------------------
log "Pre-flight checks"

if ! kubectl get ns "$NS" >/dev/null 2>&1; then
  err "namespace '$NS' does not exist; run create-secrets.sh + deploy-all.sh first"
  exit 1
fi
ok "namespace $NS exists"

if ! kubectl -n "$NS" get secret minio-secret >/dev/null 2>&1; then
  err "secret 'minio-secret' missing in namespace $NS; run create-secrets.sh"
  exit 1
fi
ok "minio-secret exists in $NS"

# We don't have `mc` in the script's runtime, so we don't probe MinIO directly.
# The user has confirmed s3://moderation-data/raw/jigsaw/train.csv exists from
# their prior baseline training success. If it disappears, the Jobs below will
# fail at the seed CSV download step with a clear error in their logs.

#------------------------------------------------------------------------------
# Cleanup any prior sweep Jobs (so a re-run doesn't fail with "already exists")
#------------------------------------------------------------------------------
log "Cleaning up any prior sweep Jobs"
for cfg in "${CONFIGS[@]}"; do
  if kubectl -n "$NS" get job "ml-sweep-$cfg" >/dev/null 2>&1; then
    kubectl -n "$NS" delete job "ml-sweep-$cfg" --wait=true
    ok "deleted prior ml-sweep-$cfg"
  fi
done

#------------------------------------------------------------------------------
# Run each config sequentially
#------------------------------------------------------------------------------
# Initialize as empty arrays (not just declared) so `set -u` doesn't trip
# on `${FAILED[*]}` when no Jobs failed.
SUCCEEDED=()
FAILED=()

for cfg in "${CONFIGS[@]}"; do
  log "Training config: $cfg"
  manifest="$SWEEP_DIR/job-$cfg.yaml"
  job="ml-sweep-$cfg"

  if [[ ! -f "$manifest" ]]; then
    err "missing manifest $manifest"
    FAILED+=("$cfg")
    continue
  fi

  kubectl -n "$NS" apply -f "$manifest"

  # Wait for either Complete or Failed condition.
  if kubectl -n "$NS" wait --for=condition=complete --timeout="$WAIT_TIMEOUT" "job/$job" 2>/dev/null; then
    ok "$cfg: Job completed successfully"
    SUCCEEDED+=("$cfg")
  else
    err "$cfg: Job did not reach Complete within $WAIT_TIMEOUT (or failed)"
    echo "    -- last 40 log lines --"
    kubectl -n "$NS" logs "job/$job" --tail=40 || true
    echo "    -- pod status --"
    kubectl -n "$NS" get pods -l "job-name=$job" -o wide || true
    FAILED+=("$cfg")
    # Continue with remaining configs rather than abort — partial sweep is still useful.
  fi
done

#------------------------------------------------------------------------------
# Summary
#------------------------------------------------------------------------------
log "Sweep summary"
echo "  succeeded (${#SUCCEEDED[@]}): ${SUCCEEDED[*]:-<none>}"
echo "  failed    (${#FAILED[@]}): ${FAILED[*]:-<none>}"
echo
echo "Next steps:"
echo "  1. Open MLflow UI and look at experiment 'moderation'."
echo "     Each run is named after its config: small_lr_tfidf, baseline_lr_tfidf,"
echo "     bigram_lr_tfidf, balanced_lr_tfidf. Compare val_roc_auc, val_f1,"
echo "     val_recall, val_precision."
echo "  2. In the 'tfidf_logreg' registered model, you'll see new versions"
echo "     (one per config that passed quality gates)."
echo "  3. Pick a winner config and let the assistant proceed to Phase B."
echo
echo "  MLflow UI:  http://mlflow.<your-floating-ip>.nip.io  (or port-forward svc/mlflow -n platform 5000:5000)"

if [[ ${#FAILED[@]} -gt 0 ]]; then
  exit 1
fi
