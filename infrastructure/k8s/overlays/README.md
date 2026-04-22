# Kustomize overlays (staging / canary / production)

This directory is reserved for **environment-specific** patches (image tags, replica counts, ingress hostnames, resource limits) so **Argo CD** can sync one branch/path per environment.

**Target layout (to implement in a follow-up pass):**

```text
overlays/
  staging/    # kustomization.yaml + patches → e.g. image tags *-staging, namespace suffix or labels
  canary/
  production/
```

**Convention:** `base/` will either live in `../` (sibling kustomization including `apps/`, `platform/`, …) or in a new `k8s/base` aggregation — one consolidation step before turning on Argo in production.

For now, `kubectl apply` uses the default manifests under `k8s/` without overlays.

See [docs/ARCHITECTURE-MASTER-PLAN.md](../../docs/ARCHITECTURE-MASTER-PLAN.md) §5.
