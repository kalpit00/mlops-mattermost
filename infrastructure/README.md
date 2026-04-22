# Infrastructure

This directory is the source of truth for DevOps/Platform artifacts used to deploy the project on Chameleon with Terraform + OpenStack + Kubernetes.

## Directory layout

- `terraform/`: Chameleon Day 0 (VM, floating IP, volume, security groups). Blazar leases are created **outside** Terraform.
- `ansible/`: optional **Kubespray** notes for multi-node clusters (`ansible/kubespray/README.md`); K3s single-node is the default in `scripts/bootstrap-k8s.sh`.
- `k8s/`: all in-cluster YAML — see [`k8s/README.md`](k8s/README.md).
- `k8s/namespaces/`: namespace objects.
- `k8s/ingress/`, `k8s/storage/`: routing and PVCs.
- `k8s/mattermost/`, `k8s/platform/`: chat stack + **MinIO + MLflow** (shared data plane).
- `k8s/apps/serving/`, `k8s/apps/training/`: model API + training `Job` / retrain `CronJob`.
- `k8s/mlops-data/`: optional Jupyter + data pipelines; not in default `deploy-all.sh` (use `deploy-mlops-data.sh`).
- `k8s/overlays/`: future Kustomize **staging / canary / prod** (placeholders; Argo CD will target these).
- `k8s/gitops/`: Argo CD install and patterns ([`k8s/gitops/ARGO-CD-INSTALL.md`](k8s/gitops/ARGO-CD-INSTALL.md)).
- `scripts/`: bootstrap, `create-secrets.sh`, `deploy-all.sh`, FIP manifest helper, e2e checks.
- `docs/`: [SYSTEM-BRINGUP-CHECKLIST](docs/SYSTEM-BRINGUP-CHECKLIST.md), [ARCHITECTURE-MASTER-PLAN](docs/ARCHITECTURE-MASTER-PLAN.md), [ROLLBACK-BASELINE](docs/ROLLBACK-BASELINE.md), runbooks, sizing.
- `secrets.env.example` → local `secrets.env` (gitignored) for a **single** place to set DB + MinIO credentials for scripts.

## Namespaces

- `mattermost`
- `platform`
- `mlops-serving`
- `mlops-training`
- `mlops-data`

## Notes

- No secrets are committed to Git.
- `k8s/apps/*` use **example** image tags and `MODEL_S3_URI=REPLACE_ME` until CI/registry and a trained model path exist; replace as you harden the pipeline.
- These manifests are what you apply to the Chameleon-backed cluster (or what Argo CD will sync to).

## Bring-up sequence

**Full ordered checklist (all phases, secrets in one file, FIP/ingress, validation, stub → overlay migration):** [docs/SYSTEM-BRINGUP-CHECKLIST.md](docs/SYSTEM-BRINGUP-CHECKLIST.md). The checklist explains why **Terraform (VM) then K3s bootstrap** is the normal IaaS path, and how **staging/canary/prod** usually map to **Git overlays on one cluster**, not three separate VMs.  
**Secrets template:** copy [`secrets.env.example`](secrets.env.example) → `secrets.env` (gitignored), then run `create-secrets.sh` / `create-mlops-data-secrets.sh` as needed.

Condensed:

1. Provision Chameleon VM, volume, and floating IP with Terraform.
2. Attach and mount persistent volume on the VM.
3. Install/bootstrap Kubernetes (`scripts/bootstrap-k8s.sh`).
4. Install ingress controller and metrics-server (part of bootstrap script).
5. Set Floating IP in ingress/Mattermost URLs (`scripts/set-floating-ip-in-manifests.sh` or manual edit).
6. Create namespaces and storage resources; ensure secrets exist **before** `deploy-all.sh`.
7. Create secrets locally (`scripts/create-secrets.sh`; optional `create-mlops-data-secrets.sh`).
8. Deploy via `scripts/deploy-all.sh` (PostgreSQL, Mattermost, MinIO, MLflow, **apps** serving + training).
9. Verify pods, PVCs, services, and ingress resources.
10. Open service endpoints in browser and validate functionality.
11. Build/load images, wire `k8s/apps/*` (`MODEL_S3_URI`, real image tags), run training to populate MLflow/MinIO.
12. Optional data stack: `scripts/deploy-mlops-data.sh` (see `k8s/mlops-data/README.md`).
13. **GitOps:** add Kustomize **overlays** and Argo CD per [k8s/gitops/ARGO-CD-INSTALL.md](k8s/gitops/ARGO-CD-INSTALL.md) and [docs/ARCHITECTURE-MASTER-PLAN.md](docs/ARCHITECTURE-MASTER-PLAN.md).
