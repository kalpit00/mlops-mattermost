# Kubernetes manifests

Legacy/manual workload YAML for the Chameleon K3s cluster. **Apply** via `../scripts/deploy-all.sh` only when using the non-GitOps fallback.

Sprint 1 adds the preferred GitOps path under `../helm/mlops-stack` and `../argocd`: ArgoCD renders the Helm chart once per layer/environment (`platform`, `staging`, `canary`, `production`).

| Path | Workloads |
|------|-----------|
| `namespaces/` | `Namespace` objects |
| `storage/` | PVCs for Mattermost, MinIO, MLflow |
| `ingress/` | (empty) App `Ingress` objects live in `mattermost/`, `platform/`, `mlops-data/` |
| `mattermost/` | Postgres, Mattermost + `mlmoderation` sidecar, ingress — [README](mattermost/README.md) |
| `platform/` | MinIO, MLflow, ingress |
| `apps/serving/`, `apps/training/` | FastAPI (`mlops-serving:local`), training `Job` / `CronJob` (`mlops-training:local`) — [DOCKER-BUILDS.md](../docs/DOCKER-BUILDS.md) |
| `mlops-data/` | Jupyter, ingress, pipeline CronJobs — [README](mlops-data/README.md) |
| `gitops/` | Older Argo CD install notes; the active Sprint 1 GitOps manifests live in `../argocd/` |

**Architecture:** [../docs/ARCHITECTURE-MASTER-PLAN.md](../docs/ARCHITECTURE-MASTER-PLAN.md).
