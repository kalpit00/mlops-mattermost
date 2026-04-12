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

## Troubleshooting (macOS / Apple Silicon)

If `terraform init` or `terraform plan` fails with **Failed to load plugin schemas** / **Failed to read any lines from plugin's stdout** for the OpenStack provider:

1. Use the **OpenStack provider 3.x** in `providers.tf` (this repo pins `~> 3.0`).
2. Clean and re-fetch plugins: `rm -rf .terraform .terraform.lock.hcl` then `terraform init`.
3. If it still fails, clear macOS quarantine on downloaded providers:  
   `xattr -dr com.apple.quarantine .terraform/providers`
