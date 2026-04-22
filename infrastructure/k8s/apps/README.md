# Application workloads (serving + training)

First-class Kubernetes manifests for the **model API** and **training** jobs. Replace example image names and `REPLACE_ME` values with your registry tags and real `MODEL_S3_URI` as you wire CI.

| File | Kind | Namespace | Role |
| --- | --- | --- | --- |
| `serving/serving.yaml` | `Deployment`, `Service` | `mlops-serving` | FastAPI inference; initContainer pulls model from MinIO |
| `training/job-oneshot.yaml` | `Job` | `mlops-training` | Ad hoc full training run (`ml-training`) |
| `training/cronjob-retrain.yaml` | `CronJob` | `mlops-training` | Scheduled retraining |

**Prereqs:** `minio-secret` in both namespaces (see `scripts/create-secrets.sh`); platform MinIO + MLflow running.

**Build sources:** root `Dockerfile.serving`, `Dockerfile.training`; code in `serving/`, `training/`.
