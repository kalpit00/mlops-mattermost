# Infrastructure

This directory is the source of truth for DevOps/Platform artifacts used to deploy the project on Chameleon with Terraform + OpenStack + Kubernetes.

## Directory layout

- `terraform/`: Chameleon provisioning (VM, floating IP, volume, security groups).
- `scripts/`: bootstrap, secret creation, deploy, and evidence collection helpers.
- `kubernetes/namespaces/`: namespace manifests for all project domains.
- `kubernetes/ingress/`: ingress controller and ingress-related manifests.
- `kubernetes/storage/`: persistent volume and claim manifests.
- `kubernetes/mattermost/`: Mattermost and its dependency manifests.
- `kubernetes/platform/`: shared platform services (for example MinIO and MLflow).
- `kubernetes/team-stubs/`: placeholders for teammate-owned service manifests.
- `kubernetes/mlops-data/`: K8s manifests for the data team Compose stack (`docker-compose-data.yml`); not applied by default `deploy-all.sh`.
- `docs/`: sizing evidence, container matrix sources, checklists, and runbooks.

## Namespaces

- `mattermost`
- `platform`
- `mlops-serving`
- `mlops-training`
- `mlops-data`

## Notes

- No secrets are committed to Git.
- Team-owned services are represented as stubs until integrated.
- Manifests in this directory are intended to be what is actually applied on Chameleon.

## Bring-up sequence

1. Provision Chameleon VM, volume, and floating IP with Terraform.
2. Attach and mount persistent volume on the VM.
3. Install/bootstrap Kubernetes (`scripts/bootstrap-k8s.sh`).
4. Install ingress controller and metrics-server (part of bootstrap script).
5. Create namespaces and storage resources (`scripts/deploy-all.sh`).
6. Create secrets locally (`scripts/create-secrets.sh`).
7. Deploy PostgreSQL and Mattermost manifests.
8. Deploy MinIO and MLflow manifests.
9. Verify pods, PVCs, services, and ingress resources.
10. Open service endpoints in browser and validate functionality.
11. Optional data stack: `scripts/create-mlops-data-secrets.sh` then `scripts/deploy-mlops-data.sh` (see `kubernetes/mlops-data/README.md`).
