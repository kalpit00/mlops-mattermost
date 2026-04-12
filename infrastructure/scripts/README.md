# Scripts

Helper scripts for repeatable DevOps operations.

- `bootstrap-k8s.sh`: install K3s, ingress-nginx, and metrics-server.
- `create-secrets.sh`: create/update namespace secrets from local env vars.
- `deploy-all.sh`: apply manifests in bring-up order.
- `collect-evidence.sh`: export kubectl state/metrics for sizing documentation.

## Usage notes

- Run scripts from inside the target cluster node where `kubectl` is configured.
- Keep secrets in shell env or local `.env` file that is not committed.
