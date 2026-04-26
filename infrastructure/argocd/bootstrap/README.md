# ArgoCD Bootstrap

This follows the Chameleon MLOps lab pattern: install ArgoCD once, then let ArgoCD reconcile Git to the VM cluster.

## One-Time Install

```bash
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.0/manifests/install.yaml
kubectl -n argocd wait --for=condition=available deployment/argocd-server --timeout=300s
```

## Register This Repo

If the repo is public, the `Application` resources can read it directly. If it is private, add repo credentials in the ArgoCD UI or CLI before applying the applications.

```bash
kubectl apply -f infrastructure/argocd/projects/mlops.yaml
kubectl apply -f infrastructure/argocd/applications/mlops-applications.yaml
```

## UI Access

Use a local port that does not collide with Mattermost, MLflow, MinIO, Jupyter, or serving smoke tests:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
kubectl -n argocd port-forward svc/argocd-server 18080:443
```

Open `https://localhost:18080`, user `admin`.

For a live demo, expose ArgoCD through the cluster ingress controller:

```bash
kubectl apply -f infrastructure/argocd/bootstrap/argocd-ingress.yaml
kubectl -n argocd get ingress argocd-server
```

Open `https://argocd.129-114-27-105.nip.io` or `http://argocd.129-114-27-105.nip.io`, user `admin`. If the browser warns about TLS, continue; the demo ingress forwards to ArgoCD's self-signed HTTPS service.

## Applications

- `mlops-platform` manages `platform` (`MinIO`, `MLflow`, PVCs, platform ingress) and auto-syncs.
- `mlops-staging` manages `mlops-staging` serving with `MODEL_ALIAS=staging` and auto-syncs.
- `mlops-canary` manages `mlops-canary` serving with `MODEL_ALIAS=canary` and is manually synced.
- `mlops-production` manages the existing production namespaces (`mattermost`, `mlops-serving`, `mlops-training`, `mlops-data`) and is manually synced.

Secrets remain a human bootstrap step via `infrastructure/scripts/create-secrets.sh` and `infrastructure/scripts/create-mlops-data-secrets.sh`.
