# Sprint 2 Observability Runbook

This is the VM-side path for deploying the final observability layer after pushing the Sprint 2 commit.

## What Sprint 2 Adds

- Prometheus, Grafana, Alertmanager, kube-state-metrics, node exporter.
- Loki + promtail for pod logs.
- Prometheus Pushgateway for `mlops-data` drift/quality batch metrics.
- `/metrics` on `ml-serving`.
- `/api/v4/mlmoderation/metrics` on Mattermost for moderation-specific metrics.
- ServiceMonitors, Grafana dashboard, and Prometheus alert rules.
- Production serving HPA based on CPU.

## 1. Pull And Build Images

```bash
cd ~/mlops-mattermost
git pull

docker build -f Dockerfile.serving -t kalpit00/mlops-serving:v3 .
docker build -f Dockerfile.pipelines -t kalpit00/mlops-pipelines:v1 .
docker build -f server/build/Dockerfile.mlops -t kalpit00/mattermost-mlops:v5 .
```

If using the local K3s image store instead of pulling from Docker Hub:

```bash
docker save kalpit00/mlops-serving:v3 -o /tmp/mlops-serving-v3.tar
docker save kalpit00/mlops-pipelines:v1 -o /tmp/mlops-pipelines-v1.tar
docker save kalpit00/mattermost-mlops:v5 -o /tmp/mattermost-mlops-v5.tar
sudo k3s ctr images import /tmp/mlops-serving-v3.tar
sudo k3s ctr images import /tmp/mlops-pipelines-v1.tar
sudo k3s ctr images import /tmp/mattermost-mlops-v5.tar
```

If pushing to Docker Hub instead:

```bash
docker push kalpit00/mlops-serving:v3
docker push kalpit00/mlops-pipelines:v1
docker push kalpit00/mattermost-mlops:v5
```

## 2. Render Helm Charts

```bash
helm dependency update infrastructure/helm/observability-stack
helm lint infrastructure/helm/observability-stack
helm template mlops-observability infrastructure/helm/observability-stack \
  --namespace observability >/tmp/mlops-observability.yaml

helm lint infrastructure/helm/mlops-stack
helm template mlops-production infrastructure/helm/mlops-stack \
  -f infrastructure/helm/mlops-stack/values/production.yaml >/tmp/mlops-production.yaml
```

Install or upgrade the Prometheus Operator CRDs once with server-side apply. The observability chart does not let ArgoCD own these CRDs because several exceed the client-side annotation size limit.

```bash
mkdir -p /tmp/kps && cd /tmp/kps
tar xzf ~/mlops-mattermost/infrastructure/helm/observability-stack/charts/kube-prometheus-stack-*.tgz
kubectl apply --server-side --force-conflicts \
  -f /tmp/kps/kube-prometheus-stack/charts/crds/crds/
```

## 3. Apply ArgoCD Application

```bash
set -a && source infrastructure/.env && set +a
./infrastructure/scripts/create-secrets.sh
kubectl apply -f infrastructure/argocd/applications/observability.yaml
kubectl get application -n argocd
```

Sync `mlops-observability` in the ArgoCD UI or with:

```bash
kubectl -n argocd patch application mlops-observability \
  --type merge \
  -p '{"operation":{"sync":{"revision":"master","prune":true}}}'
```

Then sync production so it picks up the new image tags, Service labels, drift monitor env, and HPA:

```bash
kubectl -n argocd patch application mlops-production \
  --type merge \
  -p '{"operation":{"sync":{"revision":"master","prune":true}}}'
```

Optional: sync staging/canary if you want `/metrics` there too:

```bash
kubectl -n argocd patch application mlops-staging \
  --type merge \
  -p '{"operation":{"sync":{"revision":"master","prune":true}}}'
kubectl -n argocd patch application mlops-canary \
  --type merge \
  -p '{"operation":{"sync":{"revision":"master","prune":true}}}'
```

## 4. Wait For Workloads

```bash
kubectl get pods -n observability
kubectl get pods -n mlops-serving
kubectl get pods -n mattermost
kubectl get hpa -n mlops-serving
```

## 5. Generate Metrics

Send a few score requests:

```bash
kubectl -n mlops-serving port-forward svc/ml-serving 18000:8000 >/tmp/pf-prod.log 2>&1 &
curl -s http://localhost:18000/score -H 'Content-Type: application/json' -d '{"text":"you are awful"}'
curl -s http://localhost:18000/metrics | grep 'ml_serving_'
```

Generate moderation feedback by posting a toxic message in Mattermost, opening `/<team>/moderation`, and recording a decision. Then:

```bash
kubectl -n mattermost port-forward svc/mattermost 18065:80 >/tmp/pf-mm.log 2>&1 &
curl -s http://localhost:18065/api/v4/mlmoderation/metrics | grep 'mlmoderation_'
```

Run one drift monitor job:

```bash
kubectl -n mlops-data create job \
  --from=cronjob/mlops-drift-monitor \
  mlops-drift-monitor-manual-$(date +%s)
kubectl -n mlops-data get jobs
```

## 6. Access Dashboards

```bash
kubectl -n observability get svc
kubectl -n observability port-forward svc/kube-prometheus-stack-grafana 13000:80
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 19090:9090
kubectl -n observability port-forward svc/mlops-observability-loki 13100:3100
kubectl -n observability port-forward svc/prometheus-pushgateway 19091:9091
```

Grafana: `http://localhost:13000`, using `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` from `infrastructure/.env`.

Public demo URLs through `ingress-nginx`:

```text
http://grafana.129-114-27-105.nip.io
http://prometheus.129-114-27-105.nip.io
http://alertmanager.129-114-27-105.nip.io
http://loki.129-114-27-105.nip.io/ready
http://pushgateway.129-114-27-105.nip.io
```

Use the `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` values from `infrastructure/.env`.

Prometheus checks:

- `ml_serving_predictions_total`
- `mlmoderation_feedback_decisions_total`
- `mlops_monitor_any_breach`
- `kube_pod_container_status_restarts_total`

Loki check in Grafana Explore:

```logql
{namespace=~"mattermost|mlops-serving|mlops-data"}
```

## Completion Criteria

- `mlops-observability` is `Synced` and `Healthy`.
- Grafana dashboard loads.
- Prometheus has `ml_serving_*`, `mlmoderation_*`, and `mlops_monitor_*` metrics.
- Loki shows logs from Mattermost, serving, and `mlops-data`.
- Production Mattermost still scores messages and records moderator feedback.
