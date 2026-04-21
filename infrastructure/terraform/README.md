# Terraform (Chameleon/OpenStack)

Terraform in this directory provisions:

-   one compute node **or** use an existing manually created instance (`existing_instance_id`)
-   one floating IP
-   one Cinder block volume
-   security group with SSH/HTTP/HTTPS ingress

## Files

-   `providers.tf`: Terraform/provider version and OpenStack provider config
-   `variables.tf`: input variables
-   `main.tf`: OpenStack resources
-   `outputs.tf`: instance/floating IP/volume outputs
-   `terraform.tfvars.example`: starter values to copy

## Usage

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and update values. For a **Blazar lease**, set **`reservation_id`** to the reservation’s **`flavor_id`** (m1.large on that lease), not the lease id or project id.
2. Configure OpenStack auth **without committing secrets**:
    - Preferred: install application-credential `clouds.yaml` at `~/.config/openstack/clouds.yaml`, or
    - Optional: copy `clouds.yaml` into this directory for convenience; it is listed in `.gitignore` and must not be pushed to Git.
3. Run:
    - `terraform init`
    - `terraform plan`
    - `terraform apply`

After apply, print the public IP:

- `terraform output -raw floating_ip`
- `terraform output -raw security_group_name` (when using a manual VM, attach this SG to the instance in Horizon)

## Manual VM (Blazar lease / “no valid host” with Terraform)

If **`reservation_id = ""`** and Terraform cannot create **`m1.large`** (or your flavor), create the instance **in Horizon** on your lease, then:

1. Copy the instance’s **Nova server UUID** (Horizon: Instance details, or `openstack server list`).
2. In **`terraform.tfvars`**: set **`existing_instance_id = "<that-uuid>"`**, **`reservation_id = ""`**, and keep **`flavor_name`** / **`image_name`** as documentation only (they are not used for the VM when `existing_instance_id` is set).
3. **Attach the security group** named **`terraform output -raw security_group_name`** (e.g. `proj17-sg`) to that instance: Horizon → instance → Security Groups → add the Terraform-managed group so SSH/80/443 match this stack.
4. Run **`terraform plan`** / **`terraform apply`**. Terraform will attach the Cinder volume, allocate the floating IP, and associate it to the VM’s network port.

## Existing Terraform state: `cluster_node` index (upgrade)

If you applied this stack **before** the `existing_instance_id` change, the instance resource may be named without `[0]`. After pulling the update, run once:

```bash
terraform state mv 'openstack_compute_instance_v2.cluster_node' 'openstack_compute_instance_v2.cluster_node[0]'
```

Skip this if `terraform plan` already shows no state errors.

## Recreate VM (new floating IP)

**Warning:** `terraform destroy` removes the compute instance, the associated volume attach, the Cinder volume, **and** the floating IP (unless you adjust state/resources). The next `terraform apply` allocates a **new** floating IP — update all `nip.io` hosts in the Kubernetes manifests.

1. From this directory: `terraform plan -destroy` (read what will be deleted).
2. `terraform destroy`
3. Confirm resources are gone in **Horizon** (Instances, Volumes, Floating IPs) if you like.
4. Fix `terraform.tfvars` (flavor / `reservation_id`) as needed, then `terraform apply`.
5. Note the new address: `terraform output -raw floating_ip`
6. From the **repo root**, run:

   ```bash
   chmod +x infrastructure/scripts/set-floating-ip-in-manifests.sh
   ./infrastructure/scripts/set-floating-ip-in-manifests.sh "$(cd infrastructure/terraform && terraform output -raw floating_ip)"
   ```

   Or pass the IP you see in Horizon. Optional second argument is the **previous** dotted IP if it was not `129.114.25.58`.

7. `git diff`, commit, push. On the VM: `git pull`, `./infrastructure/scripts/bootstrap-k8s.sh` (if a fresh OS), `create-secrets.sh`, `deploy-all.sh`, `deploy-mlops-data.sh`.

## Troubleshooting (macOS / Apple Silicon)

If `terraform init` or `terraform plan` fails with **Failed to load plugin schemas** / **Failed to read any lines from plugin's stdout** for the OpenStack provider:

1. Use the **OpenStack provider 3.x** in `providers.tf` (this repo pins `~> 3.0`).
2. Clean and re-fetch plugins: `rm -rf .terraform .terraform.lock.hcl` then `terraform init`.
3. If it still fails, clear macOS quarantine on downloaded providers:  
   `xattr -dr com.apple.quarantine .terraform/providers`
