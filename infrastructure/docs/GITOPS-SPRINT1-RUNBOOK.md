# Sprint 1 GitOps Runbook: ArgoCD + Helm + 3 Environments

This is the VM-side apply path after pushing/pulling the Sprint 1 commit.

## What Changes

ArgoCD reconciles this Git repo into the cluster using one Helm chart:

- `mlops-platform` -> `platform` namespace: MinIO, MLflow, PVCs, platform ingress.
- `mlops-staging` -> `mlops-staging` namespace: serving API with `MODEL_ALIAS=staging`.
- `mlops-canary` -> `mlops-canary` namespace: serving API with `MODEL_ALIAS=canary`.
- `mlops-production` -> existing production namespaces:
  - `mattermost`
  - `mlops-serving`
  - `mlops-training`
  - `mlops-data`

Production intentionally reuses the existing namespaces and PVC names so the VM does not lose Mattermost uploads, moderation JSONL logs, MLflow metadata, or MinIO artifacts.

## Safety Check

Your pre-Sprint-1 recovery commit is:

```bash
7b8db125876b94bb6209c3f58c80ca55ff7031bb
```

Do not reset to it unless you intentionally want to abandon Sprint 1 changes.

## 1. Pull Code On The VM

```bash
cd ~/mlops-mattermost
git pull
```

## 2. Confirm Helm Is Available

```bash
helm version
```

If missing:

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

## 3. Render The Chart Before Applying ArgoCD

```bash
helm lint infrastructure/helm/mlops-stack

helm template mlops-platform infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/platform.yaml >/tmp/mlops-platform.yaml

helm template mlops-staging infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/staging.yaml >/tmp/mlops-staging.yaml

helm template mlops-canary infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/canary.yaml >/tmp/mlops-canary.yaml

helm template mlops-production infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/production.yaml >/tmp/mlops-production.yaml
```

## 4. Bootstrap Secrets

ArgoCD does not create raw secrets. Keep using the existing secret scripts.

```bash
set -a && source infrastructure/.env && set +a
./infrastructure/scripts/create-secrets.sh
./infrastructure/scripts/create-mlops-data-secrets.sh
```

`create-secrets.sh` now also creates `minio-secret` in:

- `mlops-staging`
- `mlops-canary`

## 5. Install ArgoCD

```bash
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.0/manifests/install.yaml
kubectl -n argocd wait --for=condition=available deployment/argocd-server --timeout=300s
```

## 6. Apply Project And Applications

Before syncing serving environments, make sure the current known-good model version in MLflow has these aliases:

- `production`
- `staging`
- `canary`

For the first Sprint 1 rollout, all three can point at the same known-good model version. Later, staging/canary can point at candidate versions.

```bash
kubectl apply -f infrastructure/argocd/projects/mlops.yaml
kubectl apply -f infrastructure/argocd/applications/mlops-applications.yaml
```

## 7. Check ArgoCD

Use `18080` to avoid colliding with app ports.

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo

kubectl -n argocd port-forward svc/argocd-server 18080:443
```

Open `https://localhost:18080`.

For a public demo URL:

```bash
kubectl apply -f infrastructure/argocd/bootstrap/argocd-ingress.yaml
kubectl -n argocd get ingress argocd-server
```

Open `https://argocd.129-114-27-105.nip.io` or `http://argocd.129-114-27-105.nip.io`.

## 8. Check Namespaces

```bash
kubectl get ns | awk '/argocd|platform|mattermost|mlops-/ {print}'
kubectl get pods -n platform
kubectl get pods -n mattermost
kubectl get pods -n mlops-serving
kubectl get pods -n mlops-training
kubectl get pods -n mlops-data
kubectl get pods -n mlops-staging
kubectl get pods -n mlops-canary
```

Expected namespace layout:

- `argocd`
- `platform`
- `mattermost`
- `mlops-serving`
- `mlops-training`
- `mlops-data`
- `mlops-staging`
- `mlops-canary`

## 9. Smoke Test With Careful Port Forwards

Use separate local ports:

```bash
kubectl -n platform port-forward svc/mlflow 15000:5000
kubectl -n platform port-forward svc/minio 19001:9001
kubectl -n mlops-serving port-forward svc/ml-serving 18000:8000
kubectl -n mlops-staging port-forward svc/ml-serving 18001:8000
kubectl -n mlops-canary port-forward svc/ml-serving 18002:8000
kubectl -n mattermost port-forward svc/mattermost 18065:80
```

Smoke test serving:

```bash
curl -s http://localhost:18000/health
curl -s http://localhost:18001/health
curl -s http://localhost:18002/health

curl -s http://localhost:18000/score \
  -H 'Content-Type: application/json' \
  -d '{"text":"you are awful"}'
```

Open:

- ArgoCD: `https://localhost:18080`
- MLflow: `http://localhost:15000`
- MinIO console: `http://localhost:19001`
- Mattermost: `http://localhost:18065`

## 10. Demo Flow

1. Change a Helm value in Git, for example `values/staging.yaml` image tag or model alias.
2. Push to `master`.
3. ArgoCD auto-syncs staging.
4. Manually sync canary/production in ArgoCD for controlled promotion.

This mirrors the lab's platform/staging/canary/production mental model, but uses Git commits as the source of truth rather than the lab shortcut of mutating ArgoCD values through the API.
