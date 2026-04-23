# System bring-up: end-to-end path

Use this as the **ordered checklist** to take the Chameleon + Terraform + K3s stack from “provisioned” to a **fully wired** system (Mattermost, platform MinIO/MLflow, training/serving stubs, and data paths).  
Work each phase in order; later phases assume earlier ones are green.

**Related:** [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md) (done vs open), [chameleon-runbook.md](chameleon-runbook.md) (Horizon), [`../README.md`](../README.md) (layout).

---

## What this path is (and is not)

- **Chameleon is bare IaaS:** there is no managed Kubernetes for you. **You** need at least one VM (this repo: **one** `m1.xxlarge` node) **then** you install **K3s** on that compute. Phases 1–3 are that bootstrap: **Terraform → VM + FIP + volume → K3s on the VM**. That is the normal, correct order.

- **What we are _not_ recommending:** a long-term split where the **product** (Mattermost, model service, MinIO) runs as ad hoc processes or Compose **only** on the OS, with “we’ll get to Kubernetes later.” The checklist is written so **workloads live in Kubernetes** from Phase 6 onward. Terraform does not replace Kubernetes; it only delivers the **nodes** the cluster runs on.

- **“Three environments” (staging / canary / prod):** usually **Git + one cluster** (namespaces and/or different image tags). You rarely need **three** VMs for three logical envs. See **Phase 12**.

- **App manifests in `k8s/apps/*`:** may use example tags and `MODEL_S3_URI=REPLACE_ME` until the pipeline is live—see **Phase 8** and [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md).

## Phase 0 — Preconditions

- [ ] Chameleon project active; **Application Credential** in `~/.config/openstack/clouds.yaml` (or path referenced by Terraform `openstack_cloud`).
- [ ] Local tools where you run ops: `openstack` CLI (optional), `terraform`, `kubectl`, `helm` (for bootstrap), `docker` (for image builds), SSH to the FIP/VM.
- [ ] This repo checked out; you know the **Floating IP** you will use for ingress (from Terraform output `floating_ip` after apply).

---

## Phase 1 — Blazar lease + Terraform (Day 0)

- [ ] **Create a Blazar lease** in Horizon for the instance flavor you need (target: **`m1.xxlarge`** — ~32 GiB RAM, single node for the whole stack); create **instance** reservations as required by your class/project.
- [ ] Copy the reservation **`flavor_id`** (UUID from the **Reservations** table — _not_ the lease name). It becomes Terraform `reservation_id` and maps to Nova `flavor_id`.
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
- [ ] Confirm disk space for **container images** + **Mattermost/Postgres/MLflow PVCs** (Cinder + local-path for PVCs).

---

## Phase 3 — Dev tools + Kubernetes bootstrap (K3s + ingress + metrics)

- [ ] On a **fresh** VM, run [`scripts/install-chameleon-dev-tools.sh`](../scripts/install-chameleon-dev-tools.sh) **with sudo** (Docker, git, curl, perl, jq). **Re-SSH** so the `docker` group applies.
- [ ] Run [`scripts/bootstrap-k8s.sh`](../scripts/bootstrap-k8s.sh) as a normal user (installs K3s, Helm if needed, `ingress-nginx`, metrics-server). No `kubectl`/`helm` are required *before* this script: K3s provides `kubectl`.
- [ ] `kubectl get nodes` — Ready.
- [ ] `kubectl get pods -n ingress-nginx` — controller Running.
- [ ] (Optional) Copy `kubeconfig` to teammates or use a **single** secure channel for `KUBECONFIG` + RBAC later.

---

## Phase 4 — Central secrets (single place)

**Goal:** one **documented** set of values; scripts push into Kubernetes (Secrets are still **namespace-scoped** — the scripts mirror the same logical credentials).

- [ ] Copy [`.env.example`](../.env.example) → `infrastructure/.env` (see `.gitignore` — **never commit** real values). One file contains **all** variables for both scripts.
- [ ] Fill:
    - [ ] **Postgres (Mattermost):** `MM_DB_*` — host should match the in-cluster Service (this repo: `mattermost-postgres.mattermost.svc.cluster.local`; short name `mattermost-postgres` also works from the same namespace). See [`.env.example`](../.env.example).
    - [ ] **MinIO (one logical admin user):** `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` — used for **platform** MinIO and **replicated** to other namespaces by [`scripts/create-secrets.sh`](../scripts/create-secrets.sh).
    - [ ] **Jupyter:** `DATA_JUPYTER_TOKEN` in the same `.env` file.
- [ ] `set -a && source infrastructure/.env && set +a`, then run **`./infrastructure/scripts/create-secrets.sh`** and **`./infrastructure/scripts/create-mlops-data-secrets.sh`** (required before `deploy-all.sh`).
- [ ] Verify: `kubectl -n platform get secret minio-secret`, same for `mattermost`, `mlops-training`, `mlops-serving`, **`mlops-data`**.

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

- [ ] **Secrets must exist first** (Phase 4) — preflight includes **`mlops-data`** (`minio-secret` + `data-jupyter-secret`).
- [ ] From repo: `./infrastructure/scripts/deploy-all.sh` (namespaces through **`mlops-data`**: Jupyter, pipeline CronJobs, data ingress; or same order by hand).
- [ ] **Pods:** `kubectl get pods -A` — all `Running` or expected `Completed` (Jobs).
- [ ] **PVCs bound:** especially `mlflow-data-pvc`, Mattermost, Postgres.
- [ ] **Ingresses:** `kubectl get ingress -A` — correct hosts.

---

## Phase 7 — Build and place container images

| Workload         | Source in repo                         | K8s tag (default)        |
| ---------------- | -------------------------------------- | ------------------------ |
| Mattermost MLOps | `server/build/Dockerfile.mlops`         | `mattermost-mlops:local` |
| Serving          | `Dockerfile.serving` / `serving/`       | `mlops-serving:local`    |
| Training         | `Dockerfile.training` / `training/`   | `mlops-training:local`   |
| Pipelines        | `Dockerfile.pipelines` / `data/pipelines` | `mlops-pipelines:local` (CronJobs, optional) |

- [ ] Run [`scripts/build-mlops-images.sh`](../scripts/build-mlops-images.sh) from the **repo root** on the VM, then `k3s ctr images import` (see [DOCKER-BUILDS.md](DOCKER-BUILDS.md)) **or** push to a registry and change `image:` + `imagePullSecret`.
- [ ] (Optional) Document registry name and tags in your team wiki.

**Note:** **Container images** are **not** stored in MLflow. MLflow stores **metadata** and **file artifacts** in MinIO; the serving `Deployment` still uses a **container image** for the API. See `k8s/platform/mlflow-deployment.yaml` and `k8s/apps/serving/serving.yaml`.

---

## Phase 8 — Wire team stubs (stop “empty” platform)

- [ ] **Serving:** In `k8s/apps/serving/serving.yaml`, set a real `MODEL_S3_URI` to a model object in MinIO (often an MLflow artifact path under `mlflow-artifacts/`, after a successful training run).
- [ ] **Training:** In `k8s/apps/training/cronjob-retrain.yaml` (and `job-oneshot.yaml` as needed), set schedule, `image:`, and env (`MLFLOW_TRACKING_URI`, `MLOPS_S3_*`) to match your stack.
- [ ] `kubectl apply -f` the updated files; restart Deployments as needed.
- [ ] **Mattermost → model API:** `MM_MLMODERATION_INFERENCE_URL` should point to in-cluster serving (already set in manifest to `http://ml-serving.mlops-serving.svc.cluster.local:8000/score` when that Service exists).

---

## Phase 9 — Validate data flows (non-empty MinIO / MLflow)

- [ ] **MLflow UI** (via ingress): open runs — empty until a training job logs at least one run.
- [ ] **MinIO console** (`minio.*.nip.io`): bucket `mlflow-artifacts` gets content when MLflow logs artifacts; `moderation-data` gets `mlmoderation/...` when the Mattermost sidecar mirrors logs (requires traffic + moderation features enabled).
- [ ] **End-to-end spot check:** use [`scripts/e2e-mlmoderation-minio.sh`](../scripts/e2e-mlmoderation-minio.sh) and [`scripts/README.md`](../scripts/README.md) (Mattermost message → log → MinIO) if you need automated proof.

---

## Phase 10 — `mlops-data` (Jupyter, pipelines)

- [ ] **Included in Phase 6** if you ran `create-mlops-data-secrets.sh` and `deploy-all.sh`. Re-apply this slice only: [`scripts/deploy-mlops-data.sh`](../scripts/deploy-mlops-data.sh). See [`k8s/mlops-data/README.md`](../k8s/mlops-data/README.md).

---

## Phase 11 — Post-bring-up (GitOps- and team-ready)

- [ ] **CI:** build/push images on merge; single doc on “how staging gets a new image.”
- [ ] **Argo CD (future):** install in cluster; see [`k8s/gitops/ARGO-CD-INSTALL.md`](../k8s/gitops/ARGO-CD-INSTALL.md) (path = your `infrastructure/k8s` or fork layout).
- [ ] **kubectl access:** per-teammate `KUBECONFIG` or a bastion; **RBAC** for namespace-scoped devs.
- [ ] **Backups:** Postgres volume, MinIO/MLflow PVC policy (project decision).

---

## Phase 12 — Multiple environments and GitOps (later)

- [ ] **Optionally** replace `*:local` tags with a registry, and set `MODEL_S3_URI` in `k8s/apps/serving/serving.yaml` to a real MinIO object path.
- [ ] **Three logical envs** on one cluster: duplicate **namespaces** and manifests (or use Helm / Kustomize in a *separate* branch) — not required for a first green path. Shared **`platform`** (one MinIO + MLflow) is normal.
- [ ] **Argo CD (optional):** [`k8s/gitops/ARGO-CD-INSTALL.md`](../k8s/gitops/ARGO-CD-INSTALL.md). Terraform + `bootstrap-k8s.sh` only deliver the **cluster**.
- [ ] **Capacity:** prefer a **larger flavor** (e.g. `m1.xxlarge`) before multi-node.

**Status tracker:** [PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md](PROJECT-STATUS-AGAINST-COURSE-REQUIREMENTS.md).

---

## Quick reference: scripts vs purpose

| Script                                    | Purpose                                                                                                                         |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `terraform`                               | Chameleon compute, FIP, volume, SG                                                                                              |
| `scripts/bootstrap-k8s.sh`                | K3s + ingress-nginx + metrics-server                                                                                            |
| `scripts/create-secrets.sh`               | DB + MinIO secrets across `mattermost`, `platform`, `mlops-training`, `mlops-serving`                                           |
| `scripts/create-mlops-data-secrets.sh`    | `mlops-data` namespace (Jupyter + MinIO mirror)                                                                                 |
| `scripts/deploy-all.sh`                   | Full apply through **`mlops-data`** (after both secret scripts) |
| `scripts/deploy-mlops-data.sh`            | Re-apply **only** `k8s/mlops-data` YAML |
| `scripts/set-floating-ip-in-manifests.sh` | Bulk replace FIP in nip.io hosts across ingress + Mattermost `SITEURL` (run after new `floating_ip`)                            |

---

## Secrets file (one place to edit)

- **Template:** [`.env.example`](../.env.example) — copy to `infrastructure/.env` and `source` before running `create-secrets.sh` and `create-mlops-data-secrets.sh`.
- **Rotation:** change values in `.env` (or `secrets.env`) → re-run the appropriate `create-*.sh` → restart affected pods.

This checklist is the **source of truth** for manual bring-up until GitOps (Phase 11–12) fully replaces ad-hoc applies. **Phases 1–3** are “get machines, then get Kubernetes” — that is _not_ a vote for keeping applications off Kubernetes; it is the only practical bootstrap on Chameleon.
