# Master plan: Chameleon, K3s, and app data plane

**Scope:** one **KVM@TACC** Chameleon VM (`m1.xxlarge` or similar), **single-node K3s** via `infrastructure/scripts/bootstrap-k8s.sh`, then workloads in `infrastructure/k8s/`. No multi-node automation in this repo.

---

## 1. Layers (order of concern)

| Layer                 | Responsibility                                             | Tooling in this repo                                                             |
| --------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **A. Capacity**       | Blazar lease + `flavor_id` for the VM                      | Chameleon Horizon / CLI (not Terraform)                                          |
| **B. Day 0 IaaS**     | VM, FIP, Cinder volume, security groups                    | `infrastructure/terraform/`                                                      |
| **C. Day 0.5**        | Kubernetes on that VM                                      | `infrastructure/scripts/bootstrap-k8s.sh` (K3s + ingress-nginx + metrics-server) |
| **D. Day 1 platform** | Storage, **MinIO + MLflow**, secrets                       | `infrastructure/k8s/`                                                            |
| **E. Day 1 apps**     | Mattermost + Postgres, **serving**, **training**, **mlops-data** (Jupyter) | `k8s/mattermost/`, `k8s/platform/`, `k8s/apps/`, `k8s/mlops-data/`                |
| **F. Later**          | GitOps (Argo), CI, separate envs                           | `k8s/gitops/` (notes only)                                                       |

**Order:** A → B → C once per rebuild; D → E from Git and `deploy-all.sh`.

---

## 2. Chameleon: what you provision

- **1×** Blazar **instance** reservation (e.g. **`m1.xxlarge`**); use the **reservation’s `flavor_id`** in Terraform as `reservation_id` (not the lease id).
- **OpenStack** application credentials in `clouds.yaml`, plus an SSH keypair in the project.
- This repo’s Terraform uses **sharednet1**; one FIP for ingress.

---

## 3. Services and images

| App                       | Build                           | Runs as                                   |
| ------------------------- | ------------------------------- | ----------------------------------------- |
| Mattermost (fork)         | `server/build/Dockerfile.mlops` | `Deployment` in `k8s/mattermost/`         |
| Serving                   | `Dockerfile.serving`            | `Deployment` in `k8s/apps/serving/`       |
| Training                  | `Dockerfile.training`           | `Job` / `CronJob` in `k8s/apps/training/` |
| MinIO / MLflow / Postgres | Upstream images                 | `k8s/platform/`, `k8s/mattermost/`        |

**MLflow** tracks runs; artifacts live in **MinIO** (`s3://mlflow-artifacts/…`). **Serving** pulls the `joblib` (or your artifact) via initContainer + `MODEL_S3_URI`.

---

## 4. Data flow (summary)

- **Mattermost** sidecar → `moderation-data` in MinIO (logs / feedback JSONL).
- **Training** → MLflow + MinIO reads from config (`training/configs/*.yaml`).
- **Serving** initContainer → copy model from `MODEL_S3_URI` → API pod.

Secrets: one logical MinIO user mirrored per namespace via `create-secrets.sh` (see `secrets.env.example`).

---

## 5. Environments (later)

Logical **staging / canary / prod** are often **separate namespaces** and/or **Git branches + different image tags** on the **same** cluster. Ship one working path first — see [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md).

---

## 6. GitOps (optional, after the system runs)

- `k8s/gitops/ARGO-CD-INSTALL.md` — install when you have stable images and overlays.
- **No** observability “stack” (Prometheus/Grafana, centralized logs) in the minimal bring-up; add later if required.

---

## 7. Rollback

If a refactor goes wrong, see [ROLLBACK-BASELINE.md](ROLLBACK-BASELINE.md).
