# Kubernetes manifests (cluster desired state)

All YAML for workloads that run **inside** the Chameleon-backed cluster lives here. **Terraform** only provisions the **VMs** (and FIP, volume, SG); this tree is what you `kubectl apply` or what **Argo CD** syncs.

| Path | Contents |
| --- | --- |
| `namespaces/` | `Namespace` objects |
| `storage/` | PVCs for MLflow, shared artifacts, etc. |
| `ingress/` | Ingress **routing** resources (ingress-nginx is installed by `scripts/bootstrap-k8s.sh`) |
| `platform/` | MinIO + MLflow (shared object store + experiment/artifact tracking) |
| `mattermost/` | Postgres, Mattermost, ingress for chat |
| `apps/serving/` | Model inference API (`Deployment` + `Service`) |
| `apps/training/` | One-shot training `Job`, scheduled retrain `CronJob` |
| `mlops-data/` | Optional Jupyter + pipeline CronJobs (deploy via `deploy-mlops-data.sh`) |
| `overlays/` | Placeholder for Kustomize **staging / canary / prod** (see `README.md` there) |
| `gitops/` | Argo CD install notes and example `Application` manifests |

**Script entrypoint:** `infrastructure/scripts/deploy-all.sh` (apply order: namespaces → storage → ingress → secrets preflight → mattermost → platform → apps).

**Architecture:** [docs/ARCHITECTURE-MASTER-PLAN.md](../docs/ARCHITECTURE-MASTER-PLAN.md).
