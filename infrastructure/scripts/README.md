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

## E2E: Mattermost message → score log → MinIO

This repo includes `mlmoderation` hooks in the server code. The Kubernetes manifest
[`infrastructure/kubernetes/mattermost/mattermost-deployment.yaml`](../kubernetes/mattermost/mattermost-deployment.yaml)
expects you to run a Mattermost image built from this repo so it can write JSONL logs under the PVC, which the
`mlmoderation-log-uploader` sidecar mirrors into MinIO.

### Build the local Mattermost image (run on the cluster node)

From the repo root:

```bash
docker build -t mattermost-mlops:local -f server/build/Dockerfile server
```

Then re-apply the Mattermost deployment (or `deploy-all.sh`):

```bash
kubectl -n mattermost apply -f infrastructure/kubernetes/mattermost/mattermost-deployment.yaml
kubectl -n mattermost rollout status deploy/mattermost
```

### Run the E2E check (no Mattermost API creds needed)

The script polls MinIO until it sees ML moderation score logs show up in the bucket. While it’s polling, send a message
in the Mattermost UI (any channel).

```bash
chmod +x infrastructure/scripts/e2e-mlmoderation-minio.sh
./infrastructure/scripts/e2e-mlmoderation-minio.sh
```

Success looks like:
- `PASS: found online score logs in MinIO.`

If it times out, check:
- Mattermost pod contains JSONL at `/mattermost/data/mlmoderation/logs`
- Sidecar `mlmoderation-log-uploader` is running and can authenticate to MinIO
