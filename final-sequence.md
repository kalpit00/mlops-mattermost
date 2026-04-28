# Grader deployment sequence (Chameleon)

This document is the **two high-level steps** expected for this project: **(1) provision cloud resources**, then **(2) bring up the Argo CD–managed Kubernetes stack** on the VM.

Note - Phase 1 can be skipped if the resources are already provisioned on Chameleon. I have added it for completeness and demonstration for a clean setup.

**Assumptions**

- A **Blazar lease is already active** (or extended) with capacity for the instance flavor you use in Terraform. **`TF_VAR_reservation_id`** must be the reservation flavor UUID from that lease (set via Phase 1 exports, not `terraform.tfvars`).
- **Heavy images** (e.g. Mattermost) and large manifests are **already built**; graders are not required to rebuild them for a successful deploy.
- Default **Git** repository: **https://github.com/kalpit00/mlops-mattermost.git** (branch **`master`**).
- SSH user on Chameleon CC images is **`cc`**.

---

## Phase 0 — Get the repository

On the machine where you run Terraform (your laptop or a jump host with OpenStack credentials):

```bash
git clone https://github.com/kalpit00/mlops-mattermost.git
cd mlops-mattermost
git checkout master
```

---

## Phase 1 — Provision resources (Terraform)

This satisfies the course expectation of **one provisioning path** (here: **Terraform**; a python-chi notebook is an alternative the course allows, but this repo is wired for Terraform).

### OpenStack credentials (`clouds.yaml`) on KVM@TACC

Before any `terraform` command, you need a valid **`clouds.yaml`** from the **KVM@TACC** Horizon site (same flow as **Phase E** in `infrastructure/docs/chameleon-runbook.md`):

1. In the Chameleon portal, open **Experiment → KVM@TACC** and launch **Horizon** for your project.
2. Go to **Identity → Application Credentials → Create Application Credential** (e.g. name `proj17-terraform`), set an expiration, and **download the generated `clouds.yaml`**.
3. **Verify** the file targets KVM@TACC:
    - `auth_url` should be **`https://kvm.tacc.chameleoncloud.org:5000`**
    - `region_name` should be **`KVM@TACC`**
4. The **cloud name** inside `clouds.yaml` must match what Terraform uses: this repo’s provider defaults to cloud name **`openstack`**. Either name that cloud `openstack` in `clouds.yaml`, or set `openstack_cloud` in `terraform.tfvars` to match whatever name is in the file.
5. Place `clouds.yaml` where the OpenStack/Terraform client will find it (for example **`~/.config/openstack/clouds.yaml`**, or the directory from which you run `terraform`). See also `infrastructure/terraform/README.md`.

### Create or read a Blazar lease and exports (matches the MLOps lab pattern)

Terraform does not create the lease, and the repo must not commit the lease's reservation UUID. The Phase 1 helper gets that value at runtime and prints/sources it as **`TF_VAR_reservation_id`**.

From the **repository root**, with the same OpenStack venv / `OS_CLOUD` you use for `openstack token issue`, try the lab-equivalent create path:

```bash
python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair id_rsa \
  <unique-lease-name> m1.xxlarge <hours> [--prefix proj17]
```

If local Horizon **application credential** auth rejects lease creation with **`application_credential is not allowed for managing trusts`**, create the lease in **Horizon → Reservations → Leases** using the same flavor/amount, then use the same script to dynamically extract the reservation flavor id. Exact name:

```bash
python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair id_rsa \
  --existing-lease <horizon-lease-name> [--prefix proj17]
```

`--keypair` is required: the **Horizon key pair name** (same value as the lab’s `TF_VAR_key`). Do not put the keypair in `terraform.tfvars`; use only the printed `export TF_VAR_keypair_name=...`.

The script prints **`export`** lines. **Source them in the same shell** before `terraform` (reservation id, keypair, and optional prefix).

|-----------------------------------|-------------------------|
| `TF_VAR_reservation` | `TF_VAR_reservation_id` |
| `TF_VAR_suffix` | `TF_VAR_prefix` |
| `TF_VAR_key` | `TF_VAR_keypair_name` |

**Jupyter:** `infrastructure/scripts/chameleon_mlops_lease.ipynb` (cwd = repo root).

### Terraform apply

1. From the repo root:

    ```bash
    cd infrastructure/terraform
    cp terraform.tfvars.example terraform.tfvars
    # Ensure Phase 1 exports are already in this shell (TF_VAR_reservation_id, TF_VAR_keypair_name). Edit tfvars only for image, network, etc.
    terraform init
    terraform plan
    terraform apply
    ```

2. Record the **floating IP**. Treat this as Phase 1 output only; do not assume any previous floating IP survived teardown:

    ```bash
    terraform output -raw floating_ip
    ```

Do **not** manually hard-code this into Terraform inputs. The hostname/manifests update is a **Phase 2 GitOps step**.

### Phase 2 handoff: floating IP manifests and GitOps

After Terraform prints the new floating IP, update the `nip.io` hostnames in the repository and push that change to `master` so ArgoCD can sync the new public hosts:

    ```bash
    # From repository root (not inside terraform/)
    ./infrastructure/scripts/set-floating-ip-in-manifests.sh "$(cd infrastructure/terraform && terraform output -raw floating_ip)" [<OLD_FLOAT_IP>]
    git diff
    git add infrastructure
    git commit -m "Update Chameleon floating IP"
    git push origin master
    ```

The helper script replaces the dotted IP across Helm values, ingress manifests, and `infrastructure/.env.example`. If you omit the old IP, the script uses its documented default; pass the second argument when the previous committed IP differs. ArgoCD watches `https://github.com/kalpit00/mlops-mattermost.git`, so the push is what makes the new floating IP visible to GitOps.

3. **SSH to the VM** (after your public key is on the instance):

    ```bash
    ssh -i ~/.ssh/<your-key> cc@<FLOATING_IP>
    ```

**When Phase 1 can be skipped:** If the team’s environment is **already live** on Chameleon (same instance, lease extended, floating IP unchanged), graders may **only** verify SSH and jump to Phase 2. Accessing that instance may require each grader’s **public** SSH key to be appended to **`~cc/.ssh/authorized_keys`** on the VM (one key per line).

If anything was torn down or the FIP changed, run Phase 1 (or re-associate the known FIP per your runbook) and use the helper script when the public IP changes.

---

## Phase 2 — Kubernetes, secrets, and Argo CD (GitOps)

Run **on the VM**, from a fresh clone of the same repo (or sync `master` if the repo is already there):

```bash
git clone https://github.com/kalpit00/mlops-mattermost.git
cd mlops-mattermost
git checkout master
```

**Optional but typical on a clean CC VM:** install base tools, then bootstrap the cluster:

```bash
sudo bash infrastructure/scripts/install-chameleon-dev-tools.sh
bash infrastructure/scripts/bootstrap-k8s.sh
```

**Tooling sanity check (before `deploy-gitops-stack.sh`):** That script requires **`kubectl`**, **`helm`**, and **`python3`** on the VM. `bootstrap-k8s.sh` installs **K3s** (which provides `kubectl`) and **Helm 3** if it is missing. If kubectl can't find the cluster or python3 isn't installed, run these.

```bash
export KUBECONFIG=~/.kube/config
sudo apt-get install -y python3
```

**Environment and secrets**

1. Rename the example env file and optionally edit values (We leave this as an option to demonstrate secrets are managed cleanly and the actual credentials are not public - all credentials in this file will be used to login to the services). If you ran `set-floating-ip-in-manifests.sh` in Phase 1, `infrastructure/.env.example` in the tree should already match the current IP — still copy it.

    ```bash
    cp infrastructure/.env.example infrastructure/.env
    # Edit infrastructure/.env
    ```

2. **GitOps deploy** (installs/updates Argo CD, applies the app-of-apps pattern, and syncs). From **repository root**:

    ```bash
    bash infrastructure/scripts/deploy-gitops-stack.sh
    ```

This is the all-important script. It expects `infrastructure/.env` to exist. That is why, in step 1, we provided an example file `infrastructure/.env.example` with base credentials. These can be manually edited to stronger credentials, or alternatively an `infrastructure/.env` can be copied onto the VM via `scp`.
The `deploy-gitops-stack.sh` script invokes `create-secrets.sh` and `create-mlops-data-secrets.sh` as part of the flow.

3. **Training data and model artifacts (after deploy)** — After a reprovision, prior **training data and model artifacts are not persisted** in this demo path. **Copy or upload** `raw/jigsaw/train.csv` into MinIO at **`moderation-data/raw/jigsaw/train.csv`**, then run the commands below: they **retrain all four sweep configs**, **set MLflow aliases**, and **restart serving** so inference is live again.

    ```bash
    chmod +x infrastructure/scripts/run-sweep-and-wire-inference.sh
    ./infrastructure/scripts/run-sweep-and-wire-inference.sh
    ```

4. **Scheduled retrain (manual Job) → MLflow alias → serving rollout** — To run the same training as the CronJob once, promote the new version in MLflow (e.g. point the **`production`** alias at it), reload serving, and confirm which registry version the init container resolved:

    ```bash
    kubectl -n mlops-training create job \
      --from=cronjob/ml-training-retrain "ml-training-manual-$(date +%s)"

    kubectl -n mlops-serving rollout restart deployment/ml-serving

    kubectl -n mlops-serving logs deploy/ml-serving -c fetch-model
    ```

**Verification**

**Cluster health:** to confirm the node is Ready and workloads are running.

```bash
kubectl get nodes
kubectl get pods -A
```

- **Demo URLs** (click the URL; after `set-floating-ip-in-manifests.sh` / `.env.example` match this floating IP, replace the host in your own deployment if it differs):
- The demo credentials are in `infrastructure/.env.example`
    - Mattermost : [http://129-114-27-105.nip.io](http://129-114-27-105.nip.io)
    - MLflow : [http://mlflow.129-114-27-105.nip.io](http://mlflow.129-114-27-105.nip.io)
    - MinIO : [http://minio.129-114-27-105.nip.io](http://minio.129-114-27-105.nip.io)
    - Grafana : [http://grafana.129-114-27-105.nip.io](http://grafana.129-114-27-105.nip.io)
    - Prometheus : [http://prometheus.129-114-27-105.nip.io](http://prometheus.129-114-27-105.nip.io)
    - Argo CD : [http://argocd.129-114-27-105.nip.io](http://argocd.129-114-27-105.nip.io)
    - Alertmanager : [http://alertmanager.129-114-27-105.nip.io](http://alertmanager.129-114-27-105.nip.io)
    - Loki (ready check) : [http://loki.129-114-27-105.nip.io/ready](http://loki.129-114-27-105.nip.io/ready)
    - Pushgateway : [http://pushgateway.129-114-27-105.nip.io](http://pushgateway.129-114-27-105.nip.io)
    - Jupyter : [http://data-jupyter.129-114-27-105.nip.io](http://data-jupyter.129-114-27-105.nip.io)

---

## In a Nutshell

| Rubric item                                      | This repository                                                                                                                                       |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **(1) Provisioning** — Terraform                 | **Terraform** under `infrastructure/terraform/` plus optional `./infrastructure/scripts/set-floating-ip-in-manifests.sh` when the floating IP changes |
| **(2) Runtime** — **Argo CD–managed Kubernetes** | **`bash infrastructure/scripts/deploy-gitops-stack.sh`** after `.env` setup                                                                           |

---

## Quick reference

| Artifact                      | Location / command                                                                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Blazar lease + TF_VAR exports | `python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair <horizon-name> …` (then source prints before Terraform)  |
| Terraform template            | `infrastructure/terraform/terraform.tfvars.example` → copy to `infrastructure/terraform/terraform.tfvars` (no keypair / reservation)  |
| Terraform init / plan / apply | `terraform init` → `terraform plan` → `terraform apply`                                                                               |
| Floating IP output            | `terraform output -raw floating_ip`                                                                                                   |
| FIP → manifests / examples    | `./infrastructure/scripts/set-floating-ip-in-manifests.sh`                                                                            |
| VM bootstrap                  | `infrastructure/scripts/install-chameleon-dev-tools.sh`, `infrastructure/scripts/bootstrap-k8s.sh`, `sudo apt-get install -y python3` |
| Secrets template              | `infrastructure/.env.example` → copy to `infrastructure/.env`                                                                         |
| GitOps bring-up               | `bash infrastructure/scripts/deploy-gitops-stack.sh`                                                                                  |
