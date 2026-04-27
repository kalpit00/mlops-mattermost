# Grader deployment sequence (Chameleon)

This document is the **two high-level steps** expected for this project: **(1) provision cloud resources**, then **(2) bring up the Argo CD–managed Kubernetes stack** on the VM.

Note - Phase 1 can be skipped if the resources are already provisioned on Chameleon. I have added it for completeness and demonstration for a clean setup.

**Assumptions**

- A **Blazar lease is already active** (or extended) with capacity for the instance flavor you use in Terraform. We are hoping the same lease that we have reserved is extended long enough so graders don't need to manually reserve a new lease. This repo’s Terraform is tied to **`reservation_id`** in `terraform.tfvars` (the new lease’s reservation flavor UUID); a different lease usually means updating that value (and any related settings you change with it).
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

Then continue with Terraform below.

### Terraform apply

1. From the repo root:

    ```bash
    cd infrastructure/terraform
    cp terraform.tfvars.example terraform.tfvars
    # Edit terraform.tfvars: keypair_name, reservation_id (lease flavor UUID) or existing_instance_id, etc.
    # The example file includes the base configs; adjust for a new lease, keypair, or flavor if you need more compute, volume size, or memory.
    terraform init
    terraform plan
    terraform apply
    ```

2. Record the **floating IP**:

    ```bash
    terraform output -raw floating_ip
    ```

**Optional** - **If the floating IP changed** (new IP vs what is encoded in nip.io hostnames and examples), update the repo **before** Phase 2 so ingress URLs and `.env.example` patterns stay consistent:

    ```bash
    # From repository root (not inside terraform/)
    ./infrastructure/scripts/set-floating-ip-in-manifests.sh <NEW_FLOAT_IP> [<OLD_FLOAT_IP>]
    ```

The helper script replaces the dotted IP across Helm values, ingress manifests, and `infrastructure/.env.example`. If you omit the old IP, the script uses its documented default—override with the second argument if your previous IP was different.
Please note - running this script means the graders might need to require push access as the change would only be made locally. ArgoCD is implemented to watch the main repo `https://github.com/kalpit00/mlops-mattermost.git`.

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

**Verification**

**Cluster health:** to confirm the node is Ready and workloads are running.

```bash
kubectl get nodes
kubectl get pods -A
```

- **Demo URLs** (click the URL; after `set-floating-ip-in-manifests.sh` / `.env.example` match this floating IP, replace the host in your own deployment if it differs):
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
| Terraform template            | `infrastructure/terraform/terraform.tfvars.example` → copy to `infrastructure/terraform/terraform.tfvars`                             |
| Terraform init / plan / apply | `terraform init` → `terraform plan` → `terraform apply`                                                                               |
| Floating IP output            | `terraform output -raw floating_ip`                                                                                                   |
| FIP → manifests / examples    | `./infrastructure/scripts/set-floating-ip-in-manifests.sh`                                                                            |
| VM bootstrap                  | `infrastructure/scripts/install-chameleon-dev-tools.sh`, `infrastructure/scripts/bootstrap-k8s.sh`, `sudo apt-get install -y python3` |
| Secrets template              | `infrastructure/.env.example` → copy to `infrastructure/.env`                                                                         |
| GitOps bring-up               | `bash infrastructure/scripts/deploy-gitops-stack.sh`                                                                                  |
