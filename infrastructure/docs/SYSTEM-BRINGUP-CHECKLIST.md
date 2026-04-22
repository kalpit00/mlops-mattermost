# System bring-up: end-to-end path

Use this as the **ordered checklist** to take the Chameleon + Terraform + K3s stack from “provisioned” to a **fully wired** system (Mattermost, platform MinIO/MLflow, training/serving stubs, and data paths).  
Work each phase in order; later phases assume earlier ones are green.

**Related:** [demo-checklist.md](demo-checklist.md) (short demo-only list), [chameleon-runbook.md](chameleon-runbook.md) (Chameleon/Horizon), [`../README.md`](../README.md) (repo layout).

---

## What this path is (and is not)

- **Chameleon is bare IaaS:** there is no managed Kubernetes for you. **Something** must be a VM (or three) first; **then** you install Kubernetes on that compute. Phases 1–3 are that bootstrap: **Terraform → VM + FIP + volume → K3s on the VM(s)**. That is the normal, correct order.

- **What we are *not* recommending:** a long-term split where the **product** (Mattermost, model service, MinIO) runs as ad hoc processes or Compose **only** on the OS, with “we’ll get to Kubernetes later.” The checklist is written so **workloads live in Kubernetes** from Phase 6 onward. Terraform does not replace Kubernetes; it only delivers the **nodes** the cluster runs on.

- **“Three environments” (staging / canary / prod):** in most class and small-team setups that is a **Git + cluster** concern first: **separate namespaces** and/or **Kustomize/Helm overlays** (or three Argo CD `Application`s) **on the same cluster**. You can add a second or third *cluster* later if the project outgrows one control plane, but you do not need **three** Chameleon VMs *just* to get three *logical* environments. When you are ready, the MLOps-lab style layout is `overlays/staging|canary|prod` (under `infrastructure/k8s/`) in Git, not “three separate Terraform root modules” by default.

- **App manifests in `k8s/apps/*` (example image tags, optional `MODEL_S3_URI=REPLACE_ME`):** safe defaults until CI/registry and a trained model path exist. Plan to add **Kustomize overlays** under `k8s/overlays/{staging,canary,prod}` and point **Argo CD** at that tree—see **Phase 12** below.

## Phase 0 — Preconditions

- [ ] Chameleon project active; **Application Credential** in `~/.config/openstack/clouds.yaml` (or path referenced by Terraform `openstack_cloud`).
- [ ] Local tools where you run ops: `openstack` CLI (optional), `terraform`, `kubectl`, `helm` (for bootstrap), `docker` (for image builds), SSH to the FIP/VM.
- [ ] This repo checked out; you know the **Floating IP** you will use for ingress (from Terraform output `floating_ip` after apply).

---

## Phase 1 — Blazar lease + Terraform (Day 0)

- [ ] **Create a Blazar lease** in Horizon for the instance flavor you need (e.g. `m1.large`); create **instance** reservations as required by your class/project.
- [ ] Copy the reservation **`flavor_id`** (UUID from the **Reservations** table — *not* the lease name). It becomes Terraform `reservation_id` and maps to Nova `flavor_id`.
- [ ] Copy [`terraform/terraform.tfvars.example`](../terraform/terraform.tfvars.example) → `terraform.tfvars` (gitignored). Set:
  - [ ] `reservation_id` = that UUID **or** `existing_instance_id` if the VM is created manually.
  - [ ] `keypair_name` = your OpenStack keypair name.
  - [ ] `image_name`, `network_name`, `external_network_name`, `prefix`, `volume_size_gb` as needed.
- [ ] `terraform init` / `plan` / `apply`.
- [ ] Note outputs: **`floating_ip`**, `instance_id`, `security_group_name` (if attaching SG to a manual instance).
- [ ] If the instance was **manual**, attach the Terraform security group to the instance (SSH/80/443 per your SG rules).
- [ ] **SSH** to the VM (for bootstrap). Plan **team access** (append teammates’ public keys to `~/.ssh/authorized_keys` on the VM, or a shared org key policy).

**Docs:** [terraform/README.md](../terraform/README.md).

---

## Phase 2 — Data volume on the VM (if required for K3s or persistence)

- [ ] Terraform attaches a **Cinder volume**; ensure it is **mounted** where you keep long-lived data if your runbook does not auto-mount (e.g. `/var/lib/rancher/k3s` on dedicated disk, or extraneous PVC paths — align with your ops notes).
- [ ] Confirm disk space for **container images** + **Mattermost/Postgres/MLflow PVCs** (see sizing docs if needed: [infra-sizing-notes.md](infra-sizing-notes.md)).

---

## Phase 3 — Kubernetes bootstrap (K3s + ingress + metrics)

- [ ] On the VM, run [`scripts/bootstrap-k8s.sh`](../scripts/bootstrap-k8s.sh) (installs K3s, `ingress-nginx` via Helm, metrics-server).
- [ ] `kubectl get nodes` — Ready.
- [ ] `kubectl get pods -n ingress-nginx` — controller Running.
- [ ] (Optional) Copy `kubeconfig` to teammates or use a **single** secure channel for `KUBECONFIG` + RBAC later.

---

## Phase 4 — Central secrets (single place)

**Goal:** one **documented** set of values; scripts push into Kubernetes (Secrets are still **namespace-scoped** — the scripts mirror the same logical credentials).

- [ ] Copy [`secrets.env.example`](../secrets.env.example) → `infrastructure/secrets.env` (see `.gitignore` — **never commit** real values).
- [ ] Fill:
  - [ ] **Postgres (Mattermost):** `MM_DB_*` — host should match the in-cluster Service (this repo: `mattermost-postgres.mattermost.svc.cluster.local`; see `secrets.env.example`).
  - [ ] **MinIO (one logical admin user):** `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` — used for **platform** MinIO and **replicated** to other namespaces by [`scripts/create-secrets.sh`](../scripts/create-secrets.sh).
- [ ] `source infrastructure/secrets.env` (or export manually), then run **`./infrastructure/scripts/create-secrets.sh`**.
- [ ] (Optional) For **Jupyter + mlops-data** namespace: set `DATA_JUPYTER_TOKEN` and run **`./infrastructure/scripts/create-mlops-data-secrets.sh`**.
- [ ] Verify: `kubectl -n platform get secret minio-secret`, same for `mattermost`, `mlops-training`, `mlops-serving` (and `mlops-data` if used).

**Rule:** if you **rotate** MinIO credentials, re-run the relevant script(s) and **restart** workloads that read `minio-secret` (Mattermost sidecar, MLflow, training, serving initContainer).

---

## Phase 5 — Ingress hostnames = your Floating IP (critical)

MinIO, MLflow, and Mattermost ingresses use **nip.io** hostnames derived from the **FIP** (dashes, not dots).

- [ ] Take Terraform `floating_ip` (e.g. `203.0.113.10` → host segment `203-0-113-10`).
- [ ] **Update every host that embeds the FIP.** Prefer the helper (from repo root) after you know the new address from `terraform output -raw floating_ip`:
  - [ ] `./infrastructure/scripts/set-floating-ip-in-manifests.sh <NEW_FLOAT_IP> [<OLD_FLOAT_IP>]`
  - [ ] It edits Mattermost + platform (and **mlops-data**) ingresses/READMEs. Review `git diff` before commit/apply.
- [ ] **Manual spot-check** if you changed FIP without the script: `k8s/mattermost/mattermost-ingress.yaml`, `mattermost-deployment.yaml` (`MM_SERVICESETTINGS_SITEURL`), `k8s/platform/platform-ingress.yaml`, and any other `nip.io` references.
- [ ] Re-apply: `kubectl apply -f` the changed files (or re-run `deploy-all.sh`).

If this step is skipped, the browser will hit the **wrong** host or Mattermost will generate bad links.

---

## Phase 6 — Deploy the core stack

Order matches [`scripts/deploy-all.sh`](../scripts/deploy-all.sh):

- [ ] **Secrets must exist first** (Phase 4) — `deploy-all.sh` preflight checks `mattermost` + `platform` + `mlops-*` `minio-secret` and db/app secrets.
- [ ] From repo: `./infrastructure/scripts/deploy-all.sh` (or apply folders manually in the same order as the script).
- [ ] **Pods:** `kubectl get pods -A` — all `Running` or expected `Completed` (Jobs).
- [ ] **PVCs bound:** especially `mlflow-data-pvc`, Mattermost, Postgres.
- [ ] **Ingresses:** `kubectl get ingress -A` — correct hosts.

---

## Phase 7 — Build and place container images

| Workload        | Source in repo (typical)              | Image expectation in manifests                          |
| --------------- | -------------------------------------- | -------------------------------------------------------- |
| Mattermost MLOps | `server/build/Dockerfile.mlops` note in manifest | `mattermost-mlops:local` or pushed registry + `imagePull` |
| Serving          | `Dockerfile.serving` / `serving/`     | `k8s/apps/serving/serving.yaml` — example `ghcr.io/...`  |
| Training         | `Dockerfile.training` / `training/` | `k8s/apps/training/cronjob-retrain.yaml`, `job-oneshot.yaml` |

- [ ] Build Mattermost image per `mattermost-deployment.yaml` comments; **load** to K3s node (`docker save` + `ctr import`) **or** push to GHCR and set `image:` + `imagePullSecret`.
- [ ] Build and push (or load) **serving** and **training** images; update YAML `image:` and tags.
- [ ] (Optional) Document registry name and tags in [repo-artifact-usage-notes.md](repo-artifact-usage-notes.md) or your team wiki.

**Note:** **Container images** are **not** stored in MLflow. MLflow stores **experiment metadata** and **model file artifacts** in MinIO (`s3://mlflow-artifacts/...`); the serving `Deployment` still uses a **registry image** for the API plus an init step that fetches the model from S3. See `k8s/platform/README.md` and `k8s/apps/serving/serving.yaml`.

---

## Phase 8 — Wire team stubs (stop “empty” platform)

- [ ] **Serving:** In `k8s/apps/serving/serving.yaml`, set a real `MODEL_S3_URI` to a model object in MinIO (often an MLflow artifact path under `mlflow-artifacts/`, after a successful training run).
- [ ] **Training:** In `k8s/apps/training/cronjob-retrain.yaml` (and `job-oneshot.yaml` as needed), set schedule, `image:`, and env (`MLFLOW_TRACKING_URI`, `MLOPS_S3_*`) to match your stack.
- [ ] `kubectl apply -k` or `kubectl apply -f` the updated files; restart Deployments as needed.
- [ ] **Mattermost → model API:** `MM_MLMODERATION_INFERENCE_URL` should point to in-cluster serving (already set in manifest to `http://ml-serving.mlops-serving.svc.cluster.local:8000/score` when that Service exists).

---

## Phase 9 — Validate data flows (non-empty MinIO / MLflow)

- [ ] **MLflow UI** (via ingress): open runs — empty until a training job logs at least one run.
- [ ] **MinIO console** (`minio.*.nip.io`): bucket `mlflow-artifacts` gets content when MLflow logs artifacts; `moderation-data` gets `mlmoderation/...` when the Mattermost sidecar mirrors logs (requires traffic + moderation features enabled).
- [ ] **End-to-end spot check:** use [`scripts/e2e-mlmoderation-minio.sh`](../scripts/e2e-mlmoderation-minio.sh) and [`scripts/README.md`](../scripts/README.md) (Mattermost message → log → MinIO) if you need automated proof.

---

## Phase 10 — Optional `mlops-data` stack (Jupyter, extra pipelines)

- [ ] Not applied by default `deploy-all.sh`. Follow [`k8s/mlops-data/README.md`](../k8s/mlops-data/README.md) and [`scripts/deploy-mlops-data.sh`](../scripts/deploy-mlops-data.sh) after **Phase 4** (including `create-mlops-data-secrets.sh`).

---

## Phase 11 — Post-bring-up (GitOps- and team-ready)

- [ ] **CI:** build/push images on merge; single doc on “how staging gets a new image.”
- [ ] **Argo CD (future):** install in cluster; point at Git paths for `staging` / `canary` / `prod` overlays (align with MLOps lab: Terraform → Ansible/ bootstrap → Argo).
- [ ] **kubectl access:** per-teammate `KUBECONFIG` or a bastion; **RBAC** for namespace-scoped devs.
- [ ] **Backups:** Postgres volume, MinIO/MLflow PVC policy (project decision).

---

## Phase 12 — Kustomize overlays, registry tags, and three environments

Serving and training live in **`k8s/apps/*`** (no longer a separate “stubs” directory). Next steps are **overlays and GitOps**, not another folder move.

- [ ] **Replace** example `ghcr.io/example/...` and `REPLACE_ME` in `k8s/apps/` with your registry and real `MODEL_S3_URI` (or use kustomize `images:` to patch per env without editing base YAML).
- [ ] **Add** `k8s/overlays/staging|canary|prod` (see [`k8s/overlays/README.md`](../k8s/overlays/README.md)) and optionally aggregate bases under `k8s/base` for cleaner Kustomize roots.
- [ ] **Namespaces per env (recommended):** e.g. `mattermost-staging`, `mlops-serving-staging`, … *or* one namespace with labels and NetworkPolicy. Duplicate `minio-secret` / DB secrets as needed (Kubernetes does not share Secrets across namespaces).
- [ ] **Argo CD:** follow [`k8s/gitops/ARGO-CD-INSTALL.md`](../k8s/gitops/ARGO-CD-INSTALL.md); one `Application` (or app-of-apps) per overlay path. Terraform/bootstrap only delivers the **cluster**.
- [ ] **If you outgrow a single K3s node:** more instances in Terraform + **Kubespray** or k3s HA (see [`ansible/kubespray/README.md`](../ansible/kubespray/README.md)).

**Infra note:** “Scaling to three environments” in GitOps is usually **one cluster, three overlays**; “scaling the cluster” is a **separate** Terraform + bootstrap task when you need more CPU/RAM/HA.

---

## Quick reference: scripts vs purpose

| Script | Purpose |
|--------|---------|
| `terraform` | Chameleon compute, FIP, volume, SG |
| `scripts/bootstrap-k8s.sh` | K3s + ingress-nginx + metrics-server |
| `scripts/create-secrets.sh` | DB + MinIO secrets across `mattermost`, `platform`, `mlops-training`, `mlops-serving` |
| `scripts/create-mlops-data-secrets.sh` | `mlops-data` namespace (Jupyter + MinIO mirror) |
| `scripts/deploy-all.sh` | Ordered apply: namespaces → storage → ingress → **requires secrets** → mattermost → platform → `apps/serving` + `apps/training` |
| `scripts/deploy-mlops-data.sh` | Optional data stack |
| `scripts/set-floating-ip-in-manifests.sh` | Bulk replace FIP in nip.io hosts across ingress + Mattermost `SITEURL` (run after new `floating_ip`) |

---

## Secrets file (one place to edit)

- **Template:** [`secrets.env.example`](../secrets.env.example) — copy to `infrastructure/secrets.env` and `source` before running `create-secrets.sh`.
- **Rotation:** change values in `secrets.env` → re-run the appropriate `create-*.sh` → restart affected pods.

This checklist is the **source of truth** for manual bring-up until GitOps (Phase 11–12) fully replaces ad-hoc applies. **Phases 1–3** are “get machines, then get Kubernetes” — that is *not* a vote for keeping applications off Kubernetes; it is the only practical bootstrap on Chameleon.
