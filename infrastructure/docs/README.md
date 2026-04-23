# Infrastructure documentation

| Doc | Purpose |
|-----|---------|
| [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md) | **What’s done vs missing** (course-style); update as you ship. |
| [SYSTEM-BRINGUP-CHECKLIST.md](SYSTEM-BRINGUP-CHECKLIST.md) | **Full** ordered bring-up (Terraform → K3s → secrets → deploy). |
| [ARCHITECTURE-MASTER-PLAN.md](ARCHITECTURE-MASTER-PLAN.md) | Layers, services, data flow. |
| [DOCKER-BUILDS.md](DOCKER-BUILDS.md) | **All** project Dockerfiles, image tags, K3s import, serving architecture. |
| [chameleon-runbook.md](chameleon-runbook.md) | Horizon / KVM@TACC / Blazar / `clouds.yaml` alignment with labs. |
| [ROLLBACK-BASELINE.md](ROLLBACK-BASELINE.md) | Git SHA to pin if a large revert is needed. |

**Entry points:** [../README.md](../README.md) (infrastructure), [../k8s/README.md](../k8s/README.md) (manifests), [../scripts/README.md](../scripts/README.md) (builds + `deploy-all`).  
**Optional:** [../k8s/gitops/ARGO-CD-INSTALL.md](../k8s/gitops/ARGO-CD-INSTALL.md) (Argo CD, not in default path).
