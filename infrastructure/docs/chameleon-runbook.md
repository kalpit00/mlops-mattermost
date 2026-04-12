# Chameleon (CHI@UC) runbook — proj17

This runbook aligns the course materials (Hello Chameleon, Cloud Computing on Chameleon, Build an MLOps Pipeline) with this repository’s Terraform + Kubernetes path. Use project prefix **`proj17`** everywhere you would replace **`netID`** or **`kkp10045`** in the lab docs.

**Site:** **Experiment → CHI@UC** in the Chameleon portal (Horizon/OpenStack for UC).  
The PDFs often default to **KVM@TACC** for menus; substitute **CHI@UC** for the same steps.

---

## Course concepts → this project

| Course idea | What we use |
|-------------|-------------|
| Horizon | **Experiment → CHI@UC** |
| Naming | `node1-cloud-<netID>` → e.g. **`node1-cloud-proj17`** or resources prefixed with **`proj17`** via Terraform `prefix` |
| Image | **`CC-Ubuntu24.04`** (exact name, no date suffix) |
| Flavor | **`m1.medium`** or **`m1.small`** — must match your **lease** reservation |
| Tenant network | **`sharednet1`** (standard attach for Internet-facing VMs) |
| Floating IP | Pool **`public`**; associate to the instance port on **sharednet1** |
| SSH user | **`cc`** on CC images: `ssh cc@<floating-ip>` |
| Security groups | **`allow-ssh`** (22), **`allow-http-80`** (80); add **443** if you serve HTTPS |
| Leases | Cloud Computing requires a **reservation/lease** before launching a general VM; pick flavor in lease, then launch using that reserved flavor |
| Terraform auth | **Application Credentials** → **`clouds.yaml`**; for UC use **`https://chi.uc.chameleoncloud.org:5000`** and **`region_name: "CHI@UC"`** (see MLOps PDF multi-cloud example) |
| Keypairs | Upload public key per site; Terraform **`keypair_name`** = **Horizon Key Pair name** (may differ from local `id_rsa` filename) |

---

## Phase A — Project and Horizon

1. Chameleon portal: confirm the correct **project** (dropdown, e.g. **CHI-…**).
2. **Experiment → CHI@UC** → open **Horizon** if prompted.

---

## Phase B — SSH key on CHI@UC

3. **Compute → Key Pairs → Import Public Key** (or create).
4. Note the **exact keypair name** in Horizon (e.g. `id_rsa`) — this is **`keypair_name`** in `terraform.tfvars`.
5. Paste your **public** key (e.g. contents of `~/.ssh/id_rsa.pub`).

---

## Phase C — Security groups (if missing)

6. **Network → Security Groups**
   - Ensure **`allow-ssh`** (TCP 22).
   - Ensure **`allow-http-80`** (TCP 80).
   - Add rules for **TCP 443** if ingress terminates TLS on the node.

Our Terraform also creates a dedicated security group with SSH/HTTP/HTTPS; either reuse project-wide groups as in the labs or rely on Terraform — **do not** duplicate conflicting rules without checking.

---

## Phase D — Lease (reservation)

7. **Reservations → Leases → Create Lease**
   - Name example: **`lease1-proj17`** (analogous to `lease1_cloud_netID` in Cloud Computing).
   - **Flavors** tab: reserve **1×** **`m1.medium`** or **`m1.small`** (match what you will put in Terraform).
   - Set start/end times (UTC in Horizon; PDFs often use multi-hour windows).

---

## Phase E — Application credential for Terraform

8. **Identity → Application Credentials → Create Application Credential**
   - Name example: **`proj17-terraform`**.
   - Set expiration to project/class end.
   - **Download `clouds.yaml`**.

9. Verify the file targets **CHI@UC**:
   - `auth_url`: **`https://chi.uc.chameleoncloud.org:5000`**
   - `region_name`: **`CHI@UC`**
   - The **cloud** name in `clouds.yaml` must match Terraform: this repo uses `provider "openstack" { cloud = var.openstack_cloud }` with default **`openstack`**. Either name the cloud **`openstack`** in `clouds.yaml` or set `openstack_cloud` in `terraform.tfvars` to match.

10. Place `clouds.yaml` where the OpenStack/Terraform client expects it (e.g. `~/.config/openstack/clouds.yaml` or the directory from which you run `terraform`).

---

## Phase F — Terraform variables (`infrastructure/terraform/terraform.tfvars`)

Copy from `terraform.tfvars.example` and set:

| Variable | Typical value (CHI@UC) |
|----------|-------------------------|
| `openstack_cloud` | Cloud name from `clouds.yaml` (often `openstack`) |
| `prefix` | **`proj17`** |
| `image_name` | **`CC-Ubuntu24.04`** |
| `flavor_name` | **`m1.medium`** or **`m1.small`** (same as lease) |
| `keypair_name` | Horizon keypair name |
| `network_name` | **`sharednet1`** |
| `external_network_name` | **`public`** |
| `volume_size_gb` | e.g. `50` |
| `security_group_cidrs` | Prefer your public IP `/32`; labs often use `0.0.0.0/0` |

Then:

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

---

## Phase G — Floating IP (if not fully automated)

11. **Network → Floating IPs → Allocate IP to Project** → pool **`public`** → description e.g. **`Cloud IP for proj17`**.
12. **Associate** to the port for your instance on **sharednet1** (10.56.x.x style address in the course topology).

If Terraform already created and associated a floating IP, skip duplicate allocation.

---

## Phase H — SSH to the VM

13. `ssh -i ~/.ssh/id_rsa cc@<floating-ip>`  
    Adjust `-i` if your key path differs. User **`cc`** matches course Ubuntu images.

---

## Phase I — Kubernetes and workloads (this repo)

14. Copy `infrastructure/` to the VM or clone the repo; ensure scripts are executable.
15. Run in order:
    1. `infrastructure/scripts/bootstrap-k8s.sh` — K3s, ingress-nginx, metrics-server  
    2. Export env vars for `infrastructure/scripts/create-secrets.sh` (see script header)  
    3. `infrastructure/scripts/create-secrets.sh`  
    4. `infrastructure/scripts/deploy-all.sh`  
16. Verify: `kubectl get nodes`, `kubectl get pods -A`, `kubectl get pvc -A`, `kubectl get ingress -A`.
17. For grading evidence: `infrastructure/scripts/collect-evidence.sh [output-dir]`

---

## Naming cheat sheet (kkp10045 / netID → proj17)

| Course pattern | proj17 equivalent |
|----------------|-------------------|
| `node1-cloud-netID` | `node1-cloud-proj17` or Terraform-named instance with prefix **`proj17`** |
| `lease1_cloud_netID` | `lease1-proj17` |
| `private_cloud_net_netID` | Optional; this Terraform stack uses **sharednet1** only unless you add a private network later |

---

## References (in-repo PDFs)

- *Hello, Chameleon* — SSH keys per site, python-chi VM naming (`exp_name`, `username` suffix), `m1.small`, `CC-Ubuntu24.04`, floating IP, `allow-ssh`.
- *Cloud Computing on Chameleon* — Horizon, **leases**, **sharednet1**, **public** FIP pool, `allow-ssh` / `allow-http-80`, `m1.medium` lease example.
- *Build an MLOps Pipeline* — Terraform + **`clouds.yaml`**, application credentials, **CHI@UC** auth URL pattern, sharednet1 in Terraform data sources.
