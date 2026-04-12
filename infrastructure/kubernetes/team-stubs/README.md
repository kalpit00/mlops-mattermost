# Team service stubs

Minimal manifests for teammate-owned workloads **before** real images and Compose files land.

| Area | Compose / Dockerfile (source) | Kubernetes (this repo) |
|------|--------------------------------|-------------------------|
| Data (MinIO + Jupyter) | `docker-compose-data.yml` | `../mlops-data/` (full manifests; not part of default `deploy-all.sh`) |
| Training | `Dockerfile.training` | `training-stub.yaml` (`Job`, command `python train.py`) |
| Serving (API) | `Dockerfile.serving` / `Dockerfile.multiworker` | `serving-stub.yaml` (`Deployment` + `Service`, port `8000`) |

`scripts/deploy-all.sh` applies **this directory only** (for lightweight placeholders). The **mlops-data** stack is applied manually when the team wants a second MinIO + Jupyter (see `../mlops-data/README.md`).
