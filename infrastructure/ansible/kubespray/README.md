# Kubespray on Chameleon

**Kubespray** is the standard Ansible way to install a full **upstream Kubernetes** on existing Linux hosts. The MLOps class lab often vendors it as a **git submodule** inside an IAC repository.

## Add Kubespray (typical class pattern)

From a directory *outside* or *next to* this repo (or as `infrastructure/ansible/kubespray/kubespray` as a submodule — team choice):

```bash
git clone https://github.com/kubernetes-sigs/kubespray.git
cd kubespray
cp -rfp inventory/sample inventory/mycluster
# Edit inventory/mycluster/hosts.yaml with your Chameleon node IPs, groups (kube_node, etcd, kube_control_plane)
```

## Inventory hints

- **Network:** if using **sharednet1** only, all nodes need SSH from your runner to their **private** or **FIP** addresses as you prefer for Ansible. If the lab’s **192.168.1.x** private network and router are used, match that in OpenStack/Neutron (advanced Terraform; not in the current single-node Terraform).
- **Time sync:** NTP is expected; Chameleon images usually OK.
- **CNI:** Kubespray default (Calico) works; follow upstream docs.
- **Resource:** ensure flavors meet Kubespray minimums (CPU/RAM per node).

## After the cluster is up

1. Copy `admin.conf` to `~/.kube/config` and test `kubectl get nodes`.
2. Install **ingress-nginx** + **metrics-server** (mirror `infrastructure/scripts/bootstrap-k8s.sh` Helm/kubectl lines if not already in your Kubespray addons).
3. Run **`infrastructure/scripts/deploy-all.sh`** on a host with `kubectl` access to the new cluster (same as K3s path).

**Do not** commit cloud passwords or `kubeconfig` with embedded secrets to this repository.

## References

- [Kubespray — Getting started](https://kubespray.io/#/getting-started/getting-started)
- MLOps lab: Terraform provisions nodes → Kubespray in Ansible materials → then Argo CD.
