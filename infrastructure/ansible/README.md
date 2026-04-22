# Ansible (optional) — multi-node cluster with Kubespray

**Single-node K3s** is the default in this repo (`infrastructure/scripts/bootstrap-k8s.sh`).

**Multi-node, lab-style** clusters use **Kubespray** (Ansible playbooks). This directory holds **operational notes** only; the upstream project and inventory live elsewhere or as a **Git submodule** when you are ready.

## When to use Kubespray

- You need **≥2 worker nodes** (or HA control plane) on Chameleon.
- You have **leased** one VM per node (same or coordinated Blazar reservations).

## Suggested steps (outline)

1. On your control machine (laptop, Bastion, or Chameleon Jupyter if you use the lab style): `pip install ansible` in a venv.
2. **Clone** [kubernetes-sigs/kubespray](https://github.com/kubernetes-sigs/kubespray) and follow **their** docs for v2.24+ and your target Kubernetes version.
3. Build an **inventory** with your Chameleon private IPs, SSH key, and `ansible_user` (usually `ubuntu` or `cc`).
4. Run the Kubespray playbooks (`cluster.yml`) against that inventory; collect `kubeconfig` from the first control-plane node.
5. Install **ingress-nginx** and **metrics-server** (same as `bootstrap-k8s.sh` does for K3s) — or re-use the Helm invocations from that script.
6. Proceed to `infrastructure/k8s/` and `infrastructure/scripts/deploy-all.sh` unchanged.

**Terraform:** add one OpenStack `openstack_compute_instance_v2` per node, same network + SG as today; or mirror the MLOps lab’s three-node `tf` layout.

**Detail:** [kubespray/README.md](kubespray/README.md).
