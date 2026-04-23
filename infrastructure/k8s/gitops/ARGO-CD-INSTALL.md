# Argo CD on this cluster (GitOps)

Use this as the **order of operations** after the cluster and platform stack are healthy. Aligns with the MLOps lab: _Terraform_ → _bootstrap cluster_ → _Argo CD_ syncs from Git\*.

## 1. Install Argo CD (one-time)

From a machine with `kubectl` and admin on the target cluster (official install):

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

**Access UI (dev):** port-forward, or add an `Ingress` with TLS for production.

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

## 2. Register this repository

- **Argo** needs read access to the Git remote (deploy key, PAT, or public repo).
- **App manifest root:** e.g. `infrastructure/k8s` (plain YAML; or your own overlay layout outside this repo).

## 3. Create `Application` resources (pattern)

- **Option A — app of apps:** one `Application` that points at a folder of child `Application` YAMLs in Git.
- **Option B — one `Application` per service/env:** e.g. `mattermost-staging`, `platform-staging` (larger, explicit).

**Example stub** (placeholders — adjust repo URL and `path`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
    name: project-staging
    namespace: argocd
spec:
    project: default
    source:
        repoURL: https://github.com/ORG/REPO.git
        targetRevision: main
        path: infrastructure/k8s
    destination:
        server: https://kubernetes.default.svc
        namespace: default
    syncPolicy:
        automated:
            prune: true
            selfHeal: true
```

**Secrets:** do **not** put raw `minio-secret` in Git. Use:

- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets), **SOPS**, or
- [External Secrets](https://external-secrets.io/) + Vault/chosen backend, or
- Keep `create-secrets.sh` as a **human bootstrap** only and mark Argo apps as _Depends_ on that secret existing.

## 4. Image updates without Git commits (optional)

- **Argo Image Updater** to bump tags when CI pushes a new image.
- Or **only CI** that commits a new kustomize image digest (stricter, fully Git-audited).

## 5. Argo **Workflows** (optional, separate from CD)

MLOps lab uses **Argo Workflows** for _pipelines_ (retrain, batch). Install only after **Argo CD** and **Container Registry** are stable; it is a separate controller.

---

_See [docs/ARCHITECTURE-MASTER-PLAN.md](../../docs/ARCHITECTURE-MASTER-PLAN.md) for the full platform picture._
