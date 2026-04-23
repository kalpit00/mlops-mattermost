# Project status (ECE-GY 9183–style deliverables)

Living checklist for what is **implemented in repo / on Chameleon** vs **still open** for a full MLOps class submission. Update as you close gaps. Course handout: [MLOps project (FFund)](https://ffund.github.io/ml-sys-ops/docs/project.html).

---

## Implemented (repo + scripts)

| Area | Status |
|------|--------|
| **Chameleon IaaS** | `infrastructure/terraform/` — VM, FIP, Cinder attach, security group. Blazar `reservation_id` = reservation **flavor_id** row in Horizon. |
| **K3s bootstrap** | `infrastructure/scripts/bootstrap-k8s.sh` — K3s, ingress-nginx, metrics-server. |
| **Mattermost + Postgres** | `infrastructure/k8s/mattermost/` — `Dockerfile.mlops` builds **fork + webapp** (moderation UI in `webapp/.../moderation_ui`) from repo root. |
| **Platform** | `infrastructure/k8s/platform/` — MinIO + MLflow (single shared store). |
| **Serving + training** | `infrastructure/k8s/apps/serving/`, `.../training/` — FastAPI, `Job`, `CronJob`. |
| **mlops-data** | `infrastructure/k8s/mlops-data/` — Jupyter, ingress, pipeline CronJobs; **included in** `deploy-all.sh` after `create-mlops-data-secrets.sh`. |
| **Secrets** | `infrastructure/.env.example` → `.env` + `create-secrets.sh` + `create-mlops-data-secrets.sh`. |
| **Deploy** | `deploy-all.sh` — ordered `kubectl apply` of namespaces through mlops-data. |
| **FIP helper** | `set-floating-ip-in-manifests.sh` for `*.nip.io` + `MM_SERVICESETTINGS_SITEURL`. |
| **Docker** | [DOCKER-BUILDS.md](DOCKER-BUILDS.md) + [build-mlops-images.sh](../scripts/build-mlops-images.sh) — all workload tags (`*:local`) match YAML. |

---

## Gaps (typical for “system implementation” and beyond)

| Gap | Notes |
|-----|--------|
| **Load images on K3s** | `docker build` / `k3s ctr images import` (see [DOCKER-BUILDS.md](DOCKER-BUILDS.md)); optional GHCR with tag edits. |
| **Serving** | Set `MODEL_S3_URI` in `k8s/apps/serving/serving.yaml` to a real artifact in MinIO after training. |
| **End-to-end proof** | Message → log → MinIO; training run in MLflow; inference hit from Mattermost. |
| **CI/CD, three envs** | No Argo/GitOps in `deploy-all` path; add overlays or branches when required. `k8s/gitops/ARGO-CD-INSTALL.md` is reference only. |
| **Data pipelines repo** | `data/pipelines/` (if used) must be present for CI workflows; not verified here. |
| **Safeguarding** | No single doc; map fairness/explainability/privacy to what you actually ship. |
| **Monitoring / alerts** | metrics-server only; no Prometheus/Loki stack in manifests. |
| **Course write-ups / videos** | Grading artifacts out of band (Gradescope). |

---

## Single bring-up order (operator)

1. `terraform apply`  
2. On VM: `bootstrap-k8s.sh`  
3. `set-floating-ip-in-manifests.sh`  
4. `source` `infrastructure/.env` → `create-secrets.sh` **and** `create-mlops-data-secrets.sh`  
5. `build-mlops-images.sh` + `k3s ctr images import` (see [DOCKER-BUILDS.md](DOCKER-BUILDS.md))  
6. `deploy-all.sh`  

**Detail:** [SYSTEM-BRINGUP-CHECKLIST.md](SYSTEM-BRINGUP-CHECKLIST.md) — [chameleon-runbook.md](chameleon-runbook.md) (Horizon/KVM@TACC).

---

## Rollback

[ROLLBACK-BASELINE.md](ROLLBACK-BASELINE.md) — pinned commit if a large revert is needed.
