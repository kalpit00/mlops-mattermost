# Infrastructure documentation

| Doc | Purpose |
|-----|---------|
| [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md) | **What’s done vs missing** (course-style); update as you ship. |
| [SYSTEM-BRINGUP-CHECKLIST.md](SYSTEM-BRINGUP-CHECKLIST.md) | **Full** ordered bring-up (Terraform → K3s → secrets → deploy). |
| [ARCHITECTURE-MASTER-PLAN.md](ARCHITECTURE-MASTER-PLAN.md) | Layers, services, data flow. |
| [GITOPS-SPRINT1-RUNBOOK.md](GITOPS-SPRINT1-RUNBOOK.md) | VM commands for ArgoCD + Helm + platform/staging/canary/production. |
| [OBSERVABILITY-SPRINT2-RUNBOOK.md](OBSERVABILITY-SPRINT2-RUNBOOK.md) | VM commands for Prometheus/Grafana/Loki, metrics, drift monitor, and final smoke tests. |
| [DOCKER-BUILDS.md](DOCKER-BUILDS.md) | **All** project Dockerfiles, image tags, K3s import, serving architecture. |
| [chameleon-runbook.md](chameleon-runbook.md) | Horizon / KVM@TACC / Blazar / `clouds.yaml` alignment with labs. |
| [ROLLBACK-BASELINE.md](ROLLBACK-BASELINE.md) | Git SHA to pin if a large revert is needed. |

**Entry points:** [../README.md](../README.md) (infrastructure), [../helm/mlops-stack/README.md](../helm/mlops-stack/README.md) (Helm), [../argocd/bootstrap/README.md](../argocd/bootstrap/README.md) (ArgoCD), [../scripts/README.md](../scripts/README.md) (builds + secrets).
**Fallback:** [../k8s/README.md](../k8s/README.md) (legacy/manual manifests).
