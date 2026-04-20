# Training (TF‑IDF + Logistic Regression)

This folder contains the **training-owned** pipeline for the Mattermost moderation project.

## Inputs

### Seed dataset (Jigsaw)
Configured via `training/configs/*.yaml`:
- `data.seed_csv_local_path` (e.g. `/data/train.csv`), or
- `data.seed_csv_s3_uri` (e.g. `s3://moderation-data/jigsaw/train.csv`)

### Optional production feedback (Mattermost)
If you provide both URIs, training will join them to create in-domain labeled examples:
- `feedback.features_jsonl_s3_uri`: `online_features_v1.jsonl` (contains `post_id`, `text`)
- `feedback.feedback_jsonl_s3_uri`: `moderation_feedback_v1.jsonl` (contains `message_id`, `moderation_label`)

The join key is `post_id == message_id`.

## Outputs
- Logs params + metrics + artifacts to MLflow (`MLFLOW_TRACKING_URI`)
- Saves `outputs/model.joblib`, `outputs/vectorizer.joblib`, `outputs/config_used.yaml`
- Registers a model version in MLflow **only if quality gates pass** (see `gates.*` in config)

## Running (container)
Environment variables:
- `TRAIN_CONFIG=/app/training/configs/small.yaml` (or `baseline.yaml`, `balanced.yaml`, `bigram.yaml`)
- `MLFLOW_TRACKING_URI=http://mlflow.platform.svc.cluster.local:5000` (in-cluster)
- MinIO/S3 access for downloads: `MLOPS_S3_ENDPOINT`, `MLOPS_S3_ACCESS_KEY`, `MLOPS_S3_SECRET_KEY`

