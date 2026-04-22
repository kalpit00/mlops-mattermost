# Training (TF‑IDF + Logistic Regression)

This folder contains the **training-owned** pipeline for the Mattermost moderation project.

## Inputs

### Seed dataset (Jigsaw)
Configured via `training/configs/*.yaml`:
- `data.seed_csv_local_path` (e.g. `/data/train.csv`), or
- `data.seed_csv_s3_uri` (default in-repo: `s3://moderation-data/raw/jigsaw/train.csv`)

### Optional production feedback (Mattermost)
Preferred path (no join): point `feedback.feedback_jsonl_s3_uri` at:

- `s3://moderation-data/mlmoderation/feedback/moderation_feedback_v2.jsonl`

This file includes `text` + `moderation_label` and can be appended by the Mattermost server when feedback capture is enabled.

Fallback path (join): if you only have v1 feedback without text, set:

- `feedback.features_jsonl_s3_uri`: `online_features_v1.jsonl` (contains `post_id`, `text`)
- `feedback.feedback_jsonl_s3_uri`: `moderation_feedback_v1.jsonl` (contains `message_id`, `moderation_label`)

The join key is `post_id == message_id`.

## Outputs
- Logs params + metrics + artifacts to MLflow (`MLFLOW_TRACKING_URI`)
- Saves `outputs/tfidf_logreg_pipeline.joblib` (TF‑IDF + LogReg sklearn `Pipeline`) plus `outputs/config_used.yaml`
- Registers a model version in MLflow **only if quality gates pass** (see `gates.*` in config)

## Scheduled retraining (Kubernetes)
See: `infrastructure/k8s/apps/training/cronjob-retrain.yaml` (and one-shot `job-oneshot.yaml`).

These are applied by `infrastructure/scripts/deploy-all.sh` with `k8s/apps/serving` and `k8s/apps/training`.

## Running (container)
Environment variables:
- `TRAIN_CONFIG=/app/training/configs/small.yaml` (or `baseline.yaml`, `balanced.yaml`, `bigram.yaml`)
- `MLFLOW_TRACKING_URI=http://mlflow.platform.svc.cluster.local:5000` (in-cluster)
- MinIO/S3 access for downloads: `MLOPS_S3_ENDPOINT`, `MLOPS_S3_ACCESS_KEY`, `MLOPS_S3_SECRET_KEY`

