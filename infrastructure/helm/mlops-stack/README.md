# `mlops-stack` Helm Chart

This chart packages the current VM Kubernetes architecture for ArgoCD.

It intentionally keeps the production namespaces compatible with the pre-GitOps system:

- `platform` — shared MinIO + MLflow.
- `mattermost` — Mattermost app, Mattermost Postgres, feedback/log PVC.
- `mlops-serving` — production FastAPI serving (`MODEL_ALIAS=production`).
- `mlops-training` — production retraining CronJob.
- `mlops-data` — Jupyter + data pipeline CronJobs.
- `mlops-staging` — staging FastAPI serving (`MODEL_ALIAS=staging`).
- `mlops-canary` — canary FastAPI serving (`MODEL_ALIAS=canary`).

The runtime `/data` paths are not source paths. They remain runtime storage inside containers/PVCs and are still intentionally gitignored.

## Local Render Checks

```bash
helm template mlops-platform infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/platform.yaml

helm template mlops-production infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/production.yaml
```

## Direct Helm Install/Upgrade

ArgoCD is the preferred controller, but direct Helm is useful for debugging:

```bash
helm upgrade --install mlops-platform infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/platform.yaml

helm upgrade --install mlops-production infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/production.yaml
```

Do not commit generated secrets. Run the existing secret scripts before syncing via ArgoCD or Helm.
