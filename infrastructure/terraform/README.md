# Terraform (Chameleon/OpenStack)

Terraform in this directory provisions:

-   one compute node
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

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and update values.
2. Configure OpenStack auth **without committing secrets**:
    - Preferred: install application-credential `clouds.yaml` at `~/.config/openstack/clouds.yaml`, or
    - Optional: copy `clouds.yaml` into this directory for convenience; it is listed in `.gitignore` and must not be pushed to Git.
3. Run:
    - `terraform init`
    - `terraform plan`
    - `terraform apply`

After apply, print the public IP:

- `terraform output -raw floating_ip`

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
