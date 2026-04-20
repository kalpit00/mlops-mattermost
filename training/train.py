import json
import os
import platform
import socket
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import boto3
import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got: {uri}")
    rest = uri[len("s3://"):]
    parts = rest.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    if not bucket or not key:
        raise ValueError(f"Expected s3://bucket/key, got: {uri}")
    return bucket, key


def _s3_client():
    # MinIO-compatible. For in-cluster K8s, these should come from Secrets.
    endpoint_url = _optional_env("MLOPS_S3_ENDPOINT", "")
    access_key = _optional_env("MLOPS_S3_ACCESS_KEY", "")
    secret_key = _optional_env("MLOPS_S3_SECRET_KEY", "")
    region = _optional_env("MLOPS_S3_REGION", "us-east-1")

    if not endpoint_url or not access_key or not secret_key:
        raise RuntimeError(
            "S3 client not configured. Set MLOPS_S3_ENDPOINT, "
            "MLOPS_S3_ACCESS_KEY, MLOPS_S3_SECRET_KEY."
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def _download_s3(uri: str, dest_path: str) -> None:
    s3 = _s3_client()
    bucket, key = _parse_s3_uri(uri)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    s3.download_file(bucket, key, dest_path)


def _load_config() -> dict:
    config_path = _require_env("TRAIN_CONFIG")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _load_seed_df(cfg: dict) -> pd.DataFrame:
    data_cfg = cfg["data"]
    local_path = (data_cfg.get("seed_csv_local_path") or "").strip()
    s3_uri = (data_cfg.get("seed_csv_s3_uri") or "").strip()

    if not local_path and not s3_uri:
        raise RuntimeError(
            "Config must set data.seed_csv_local_path or data.seed_csv_s3_uri"
        )

    if not local_path and s3_uri:
        local_path = "/tmp/seed.csv"
        _download_s3(s3_uri, local_path)

    df = pd.read_csv(local_path)
    text_col = data_cfg["text_column"]
    label_col = data_cfg["label_column"]
    df = df[[text_col, label_col]].dropna()
    df[label_col] = df[label_col].astype(int)
    df = df.rename(columns={text_col: "text", label_col: "label"})
    return df


def _load_feedback_joined_df(cfg: dict) -> Optional[pd.DataFrame]:
    fb_cfg = (cfg.get("feedback") or {}) if isinstance(cfg.get("feedback"), dict) else {}
    features_uri = (fb_cfg.get("features_jsonl_s3_uri") or "").strip()
    feedback_uri = (fb_cfg.get("feedback_jsonl_s3_uri") or "").strip()
    if not features_uri or not feedback_uri:
        return None

    features_path = "/tmp/online_features.jsonl"
    feedback_path = "/tmp/mod_feedback.jsonl"
    _download_s3(features_uri, features_path)
    _download_s3(feedback_uri, feedback_path)

    def read_jsonl(path: str) -> pd.DataFrame:
        rows = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return pd.DataFrame(rows)

    features = read_jsonl(features_path)
    feedback = read_jsonl(feedback_path)

    # If feedback already includes text (moderation_feedback_v2.jsonl), we can use it directly.
    if "text" in feedback.columns and "moderation_label" in feedback.columns:
        direct = feedback[["text", "moderation_label"]].copy()
        direct["label"] = direct["moderation_label"].map({"toxic": 1, "non_toxic": 0})
        direct = direct[["text", "label"]].dropna()
        direct["label"] = direct["label"].astype(int)

        max_rows = int((fb_cfg.get("max_rows") or 0) or 0)
        if max_rows > 0 and len(direct) > max_rows:
            direct = direct.sample(n=max_rows, random_state=int(cfg.get("seed", 42)))
        return direct

    # From Go schemas:
    # - FeatureRowV1: post_id, text
    # - FeedbackRowV1: message_id, moderation_label ("toxic"|"non_toxic")
    if "post_id" not in features.columns or "text" not in features.columns:
        raise RuntimeError(
            "online_features JSONL missing required fields: post_id, text"
        )
    if "message_id" not in feedback.columns or "moderation_label" not in feedback.columns:
        raise RuntimeError(
            "feedback JSONL missing required fields: message_id, moderation_label"
        )

    feedback = feedback.rename(columns={"message_id": "post_id"})
    feedback["label"] = feedback["moderation_label"].map({"toxic": 1, "non_toxic": 0})
    joined = feedback.merge(features[["post_id", "text"]], on="post_id", how="inner")
    joined = joined[["text", "label"]].dropna()
    joined["label"] = joined["label"].astype(int)

    max_rows = int((fb_cfg.get("max_rows") or 0) or 0)
    if max_rows > 0 and len(joined) > max_rows:
        joined = joined.sample(n=max_rows, random_state=int(cfg.get("seed", 42)))

    return joined


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str


def _apply_quality_gates(cfg: dict, metrics: dict) -> GateResult:
    gates = cfg.get("gates") or {}
    min_auc = float(gates.get("min_val_roc_auc", 0.0) or 0.0)
    min_recall = float(gates.get("min_val_recall", 0.0) or 0.0)

    auc = float(metrics.get("val_roc_auc", 0.0) or 0.0)
    rec = float(metrics.get("val_recall", 0.0) or 0.0)

    if auc < min_auc:
        return GateResult(False, f"val_roc_auc {auc:.4f} < gate {min_auc:.4f}")
    if rec < min_recall:
        return GateResult(False, f"val_recall {rec:.4f} < gate {min_recall:.4f}")
    return GateResult(True, "passed")


def main() -> None:
    cfg = _load_config()

    tracking_uri = _require_env("MLFLOW_TRACKING_URI")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(cfg["experiment_name"])

    seed_df = _load_seed_df(cfg)
    fb_df = _load_feedback_joined_df(cfg)
    train_df = seed_df if fb_df is None else pd.concat([seed_df, fb_df], ignore_index=True)

    X_train, X_val, y_train, y_val = train_test_split(
        train_df["text"],
        train_df["label"],
        test_size=0.2,
        random_state=int(cfg["seed"]),
        stratify=train_df["label"],
    )

    vec = TfidfVectorizer(
        max_features=int(cfg["model"]["max_features"]),
        ngram_range=tuple(cfg["model"]["ngram_range"]),
        min_df=int(cfg["model"]["min_df"]),
    )

    X_train_vec = vec.fit_transform(X_train)
    X_val_vec = vec.transform(X_val)

    model = LogisticRegression(
        C=float(cfg["model"]["C"]),
        max_iter=int(cfg["model"]["max_iter"]),
        class_weight=cfg["model"]["class_weight"],
        n_jobs=int(cfg["runtime"]["n_jobs"]),
    )

    threshold = float(cfg["threshold"])

    with mlflow.start_run(run_name=cfg["run_name"]):
        mlflow.log_params(
            {
                "seed": int(cfg["seed"]),
                "threshold": threshold,
                "vectorizer": cfg["model"]["vectorizer"],
                "max_features": int(cfg["model"]["max_features"]),
                "ngram_range": str(cfg["model"]["ngram_range"]),
                "min_df": int(cfg["model"]["min_df"]),
                "estimator": cfg["model"]["estimator"],
                "C": float(cfg["model"]["C"]),
                "class_weight": str(cfg["model"]["class_weight"]),
                "max_iter": int(cfg["model"]["max_iter"]),
                "n_jobs": int(cfg["runtime"]["n_jobs"]),
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "mlflow_tracking_uri": tracking_uri,
                "seed_rows": int(len(seed_df)),
                "feedback_rows": int(0 if fb_df is None else len(fb_df)),
            }
        )

        start_time = time.time()
        model.fit(X_train_vec, y_train)
        train_time_sec = time.time() - start_time

        val_scores = model.predict_proba(X_val_vec)[:, 1]
        val_preds = (val_scores >= threshold).astype(int)

        metrics = {
            "val_roc_auc": roc_auc_score(y_val, val_scores),
            "val_pr_auc": average_precision_score(y_val, val_scores),
            "val_accuracy": accuracy_score(y_val, val_preds),
            "val_f1": f1_score(y_val, val_preds, zero_division=0),
            "val_precision": precision_score(y_val, val_preds, zero_division=0),
            "val_recall": recall_score(y_val, val_preds, zero_division=0),
            "train_time_sec": train_time_sec,
            "train_rows": int(len(X_train)),
            "val_rows": int(len(X_val)),
            "vocab_size": int(len(vec.vocabulary_)),
        }
        mlflow.log_metrics(metrics)

        os.makedirs("outputs", exist_ok=True)

        model_path = "outputs/model.joblib"
        vectorizer_path = "outputs/vectorizer.joblib"
        config_path = "outputs/config_used.yaml"

        joblib.dump(model, model_path)
        joblib.dump(vec, vectorizer_path)
        with open(config_path, "w") as f:
            yaml.safe_dump(cfg, f)

        mlflow.log_metric("model_size_bytes", int(os.path.getsize(model_path)))
        mlflow.log_metric("vectorizer_size_bytes", int(os.path.getsize(vectorizer_path)))

        mlflow.log_artifact(model_path)
        mlflow.log_artifact(vectorizer_path)
        mlflow.log_artifact(config_path)
        mlflow.sklearn.log_model(model, artifact_path="sk_model")

        gate = _apply_quality_gates(cfg, metrics)
        mlflow.log_param("quality_gate_passed", str(gate.passed).lower())
        mlflow.log_param("quality_gate_reason", gate.reason)

        if gate.passed:
            # Minimal registry integration: register the sklearn model artifact.
            model_name = _optional_env("MLFLOW_MODEL_NAME", "tfidf_logreg")
            run_id = mlflow.active_run().info.run_id
            model_uri = f"runs:/{run_id}/sk_model"
            mv = mlflow.register_model(model_uri=model_uri, name=model_name)
            mlflow.log_param("registered_model_name", model_name)
            mlflow.log_param("registered_model_version", str(mv.version))
        else:
            print(f"Quality gate failed: {gate.reason}")

        print("Run completed.")
        print(metrics)


if __name__ == "__main__":
    main()
