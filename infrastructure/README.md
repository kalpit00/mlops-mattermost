# Infrastructure

**Chameleon (KVM@TACC):** Terraform → **one VM** (e.g. `m1.xxlarge`) → **K3s** → `kubectl` manifests in `k8s/`. **Docker plan:** [docs/DOCKER-BUILDS.md](docs/DOCKER-BUILDS.md). Status / gaps: [docs/PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](docs/PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md). Full bring-up: [docs/SYSTEM-BRINGUP-CHECKLIST.md](docs/SYSTEM-BRINGUP-CHECKLIST.md).

## Layout

- `terraform/` — VM, FIP, volume, security group. Copy **`terraform/terraform.tfvars.example` → `terraform.tfvars`**, set **`keypair_name`**, then `init` / `plan` / `apply` (see [`terraform/README.md`](terraform/README.md). **`tf.env.example`** = lease metadata + optional `TF_VAR_*` exports).
- `k8s/` — legacy/manual YAML fallback; see [`k8s/README.md`](k8s/README.md).
- `helm/` — GitOps-ready Helm charts used by ArgoCD for platform, staging, canary, production, and observability.
- `argocd/` — AppProject and Application resources for the Helm-based GitOps flow.
- `scripts/` — `build-mlops-images.sh`, `bootstrap-k8s.sh`, `create-secrets.sh`, `create-mlops-data-secrets.sh`, `deploy-all.sh`, FIP helper, e2e.
- `docs/` — [index](docs/README.md).
- **Cluster secrets (Step D):** `infrastructure/.env.example` → `infrastructure/.env` (gitignored). All `export` lines for `create-secrets.sh` and `create-mlops-data-secrets.sh` in one file. (`secrets.env` is still gitignored for legacy use.)

**Production namespaces:** `mattermost`, `platform`, `mlops-serving`, `mlops-training`, `mlops-data` (Jupyter + optional pipeline CronJobs).
**GitOps environment namespaces:** `mlops-staging`, `mlops-canary`, plus production reusing the namespaces above.

## Condensed bring-up

1. In `infrastructure/terraform/`: `terraform init` → `plan` → `apply` (prereqs in [`terraform/README.md`](terraform/README.md))  
2. On the VM: `sudo ./infrastructure/scripts/install-chameleon-dev-tools.sh` (once), re-SSH, then `./infrastructure/scripts/bootstrap-k8s.sh` (see [`scripts/README.md`](scripts/README.md))  
3. `./infrastructure/scripts/set-floating-ip-in-manifests.sh` with the **floating IP**  
4. Copy/fill `infrastructure/.env` from `.env.example`; keep it gitignored and copy it to the VM when needed.
5. **Build and import images** — `./infrastructure/scripts/build-mlops-images.sh` then `k3s ctr images import` (see [docs/DOCKER-BUILDS.md](docs/DOCKER-BUILDS.md)).  
6. Preferred GitOps path: `bash ./infrastructure/scripts/deploy-gitops-stack.sh`.
7. Manual fallback: `./infrastructure/scripts/deploy-all.sh`
8. Model serving resolves MLflow aliases per environment (`staging`, `canary`, `production`) instead of hard-coding a model URI.

**Horizon / lease how-to:** [docs/chameleon-runbook.md](docs/chameleon-runbook.md).  
**Argo / GitOps:** [argocd/bootstrap/README.md](argocd/bootstrap/README.md).
Sprint 2 observability (Prometheus, Grafana, Loki, Alertmanager, Pushgateway) is part of the preferred GitOps path via [scripts/deploy-gitops-stack.sh](scripts/deploy-gitops-stack.sh).
