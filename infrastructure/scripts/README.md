# Scripts

**Images:** [../docs/DOCKER-BUILDS.md](../docs/DOCKER-BUILDS.md) lists every Dockerfile, `*:local` tag, and `k3s ctr images import`. **Build all (on the VM, repo root):** `chmod +x infrastructure/scripts/build-mlops-images.sh && ./infrastructure/scripts/build-mlops-images.sh`

- `build-mlops-images.sh`: `docker build` for `mattermost-mlops:local`, `mlops-serving:local`, `mlops-training:local`, and `mlops-pipelines:local` if `data/pipelines` exists.
- `bootstrap-k8s.sh`: install K3s, ingress-nginx, and metrics-server.
- `create-secrets.sh`: create/update secrets (Postgres + MinIO in `mattermost`, `platform`, `mlops-training`, `mlops-serving` — same MinIO credentials everywhere for the single cluster MinIO).
- `create-mlops-data-secrets.sh`: secrets for `mlops-data` (Jupyter token + `minio-secret` mirroring platform MinIO credentials).
- `deploy-all.sh`: apply all `k8s/` manifests in order, ending with **`mlops-data/`** (requires `create-mlops-data-secrets.sh` preflight).
- `deploy-mlops-data.sh`: re-apply only `k8s/mlops-data` (after `create-mlops-data-secrets.sh`).
- `collect-evidence.sh`: export kubectl state/metrics for sizing documentation.
- `set-floating-ip-in-manifests.sh`: replace `nip.io` / `MM_SERVICESETTINGS_SITEURL` hosts after Chameleon assigns a **new** floating IP (run from repo root; see `terraform/README.md`).

## Usage notes

- Run scripts from inside the target cluster node where `kubectl` is configured.
- Keep secrets in shell env or local `.env` file that is not committed.

## E2E: Mattermost message → score log → MinIO

This repo includes `mlmoderation` hooks in the server code. The Kubernetes manifest
[`infrastructure/k8s/mattermost/mattermost-deployment.yaml`](../k8s/mattermost/mattermost-deployment.yaml)
expects you to run a Mattermost image built from this repo so it can write JSONL logs under the PVC, which the
`mlmoderation-log-uploader` sidecar mirrors into MinIO.

### Build the local Mattermost image (run on the cluster node)

**Use `server/build/Dockerfile.mlops`** (from the **repository root**) so the image includes **this fork’s webapp** (for example the custom moderation UI under `webapp/channels/src/components/moderation_ui`). The default `server/build/Dockerfile` downloads upstream enterprise binaries and does **not** embed local webapp changes.

From the repo root:

```bash
docker build -t mattermost-mlops:local -f server/build/Dockerfile.mlops .
```

The Dockerfile pins `linux/amd64` (matches most Chameleon VMs). If `docker build` on Apple Silicon is slow, that is QEMU emulation for the full build.

On K3s, load the image into containerd (adjust if you use a registry instead):

```bash
docker save mattermost-mlops:local -o /tmp/mattermost-mlops-local.tar
sudo k3s ctr images import /tmp/mattermost-mlops-local.tar
```

Then re-apply the Mattermost deployment (or `deploy-all.sh`):

```bash
kubectl -n mattermost apply -f infrastructure/k8s/mattermost/mattermost-deployment.yaml
kubectl -n mattermost rollout status deploy/mattermost
```

### Moderation UI URL (same pod as Mattermost)

The moderation pages are part of the **Mattermost web client** served by the main app on port 8065. There is no separate Kubernetes Deployment for the webapp. After you open the site URL from Ingress / `MM_SERVICESETTINGS_SITEURL`, use:

`http://<SITE_HOST>/<your_team_name>/moderation`

Example: `http://129-114-27-105.nip.io/myproject/moderation` (replace host and team name).

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
