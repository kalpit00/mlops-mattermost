# Scripts

Helper scripts for repeatable DevOps operations.

- `bootstrap-k8s.sh`: install K3s, ingress-nginx, and metrics-server.
- `create-secrets.sh`: create/update secrets (Postgres + MinIO in `mattermost`, `platform`, `mlops-training`, `mlops-serving` — same MinIO credentials everywhere for the single cluster MinIO).
- `create-mlops-data-secrets.sh`: secrets for `mlops-data` (Jupyter token + `minio-secret` mirroring platform MinIO credentials).
- `deploy-all.sh`: apply manifests in bring-up order.
- `deploy-mlops-data.sh`: apply `kubernetes/mlops-data` (after data secrets exist).
- `collect-evidence.sh`: export kubectl state/metrics for sizing documentation.
- `set-floating-ip-in-manifests.sh`: replace `nip.io` / `MM_SERVICESETTINGS_SITEURL` hosts after Chameleon assigns a **new** floating IP (run from repo root; see `terraform/README.md`).

## Usage notes

- Run scripts from inside the target cluster node where `kubectl` is configured.
- Keep secrets in shell env or local `.env` file that is not committed.
