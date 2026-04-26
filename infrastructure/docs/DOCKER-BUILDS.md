# Docker images for Chameleon (K3s)

Build **from the repository root** on the VM (or build elsewhere and `docker save` + copy). All MLOps images below use **local tags** in YAML (`*:local` + `IfNotPresent`) so you can `k3s ctr images import` without a registry.

## Architecture: model serving (no second “backend”)

- **Mattermost** calls **`http://ml-serving.mlops-serving.svc.cluster.local:8000/score`** (see `k8s/mattermost/mattermost-deployment.yaml`).
- **ml-serving** is a single **Python FastAPI** app (`serving/app/main.py`) run with **Uvicorn** in the `api` container. The **initContainer** only downloads the `joblib` (or your artifact) from **MinIO** into `emptyDir` before the API starts.
- There is **no** separate application server to deploy for scoring beyond this Deployment and its Service.

**Until `MODEL_S3_URI` in `k8s/apps/serving/serving.yaml` points at a real object in MinIO**, the initContainer will **fail** and the pod will not become Ready. Train once (Job) or place an artifact, then set the URI and re-apply.

## Image table

| In-cluster image tag    | Dockerfile / context | Build command (repo root) |
|-------------------------|----------------------|---------------------------|
| `mattermost-mlops:local` | `server/build/Dockerfile.mlops` | `docker build -f server/build/Dockerfile.mlops -t mattermost-mlops:local .` |
| `mlops-serving:local`   | `Dockerfile.serving`            | `docker build -f Dockerfile.serving -t mlops-serving:local .` |
| `mlops-training:local`  | `Dockerfile.training`            | `docker build -f Dockerfile.training -t mlops-training:local .` |
| `mlops-pipelines:local` | `Dockerfile.pipelines` (needs `mlops_data/pipelines/`) | `docker build -f Dockerfile.pipelines -t mlops-pipelines:local .` |

| Pull-only (no project build) | Upstream | Used in |
|------------------------------|----------|---------|
| `postgres:15` | Docker Hub | `k8s/mattermost/postgres-statefulset.yaml` |
| `minio/minio:latest` | Docker Hub | `k8s/platform/minio-deployment.yaml` |
| `ghcr.io/mlflow/mlflow:latest` | GHCR | `k8s/platform/mlflow-deployment.yaml` |
| `minio/mc:latest` | Docker Hub | initContainers / sidecar |
| `jupyter/base-notebook:latest` | Docker Hub | `k8s/mlops-data/jupyter-deployment.yaml` |

**Pipeline CronJobs** (`k8s/mlops-data/pipelines-cronjobs.yaml`) use `mlops-pipelines:local`; they start **suspended** until you set `suspend: false` and have a good image. Skip building if `mlops_data/pipelines` is not in the checkout.

## One-shot build (VM)

```bash
cd /path/to/mattermost   # repository root
./infrastructure/scripts/build-mlops-images.sh
```

## Load into K3s (same node that built the images)

K3s uses **containerd**; images built with `docker` are not always visible to kubelet. Import:

```bash
docker save mattermost-mlops:local mlops-serving:local mlops-training:local -o /tmp/mlops.tar
# optional: append mlops-pipelines:local to the save if built
sudo k3s ctr images import /tmp/mlops.tar
```

Or import each `docker save` separately. After import, (re)apply manifests: `./infrastructure/scripts/deploy-all.sh`.

## Registry (optional)

Replace `*:local` with e.g. `ghcr.io/<org>/mlops-serving:<tag>`, set `imagePullPolicy: Always` or add `imagePullSecrets`, and build/push in CI.
