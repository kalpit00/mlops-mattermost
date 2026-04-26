# Observability Stack

Shared cluster observability for Sprint 2:

- `kube-prometheus-stack` for Prometheus, Grafana, Alertmanager, kube-state-metrics, and node exporter.
- `loki-stack` for pod logs via promtail.
- `prometheus-pushgateway` for short-lived `mlops-data` monitoring CronJobs.
- ServiceMonitors for `ml-serving` in production/staging/canary and Mattermost moderation metrics.
- Grafana dashboard and Prometheus alert rules as code.

## VM Render Check

```bash
helm dependency update infrastructure/helm/observability-stack
helm lint infrastructure/helm/observability-stack
helm template mlops-observability infrastructure/helm/observability-stack \
  --namespace observability >/tmp/mlops-observability.yaml
```

Prometheus Operator CRDs are intentionally not rendered by this chart because several are too large for ArgoCD client-side apply annotations. Install or upgrade them once with server-side apply before syncing the ArgoCD app:

```bash
mkdir -p /tmp/kps && cd /tmp/kps
tar xzf ~/mlops-mattermost/infrastructure/helm/observability-stack/charts/kube-prometheus-stack-*.tgz
kubectl apply --server-side --force-conflicts \
  -f /tmp/kps/kube-prometheus-stack/charts/crds/crds/
```

## Port Forwards

Inspect service names after sync:

```bash
kubectl -n observability get svc
```

Typical access:

```bash
kubectl -n observability port-forward svc/kube-prometheus-stack-grafana 13000:80
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 19090:9090
kubectl -n observability port-forward svc/mlops-observability-loki 13100:3100
kubectl -n observability port-forward svc/prometheus-pushgateway 19091:9091
```

Grafana demo credentials come from `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in `infrastructure/.env`.

## Public Demo URLs

The chart also creates HTTP ingresses for one-click demo access through `ingress-nginx`:

```text
http://grafana.129-114-27-105.nip.io
http://prometheus.129-114-27-105.nip.io
http://alertmanager.129-114-27-105.nip.io
http://loki.129-114-27-105.nip.io/ready
http://pushgateway.129-114-27-105.nip.io
```

Grafana credentials come from the `grafana-admin-secret` created by `infrastructure/scripts/create-secrets.sh`.
