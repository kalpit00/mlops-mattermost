"""
Scheduled monitoring: ``python -m mlops_data.pipelines.cli_monitoring``

Typical cron (repo root)::

    MLOPS_MONITOR_TRAIN_PARQUET=data/artifacts/datasets/2026-04-05/train.parquet \\
    MLOPS_MONITOR_INGESTION_PARQUET=data/artifacts/jigsaw/transformed/comments_binary.parquet \\
    python -m mlops_data.pipelines.cli_monitoring

First run with reference file::

    MLOPS_MONITOR_WRITE_REFERENCE_FROM_TRAIN=1 \\
    MLOPS_MONITOR_TRAIN_PARQUET=.../train.parquet \\
    python -m mlops_data.pipelines.cli_monitoring

Later drift runs::

    MLOPS_MONITOR_REFERENCE_JSON=data/mlmoderation/monitoring/reference_from_train.json \\
    python -m mlops_data.pipelines.cli_monitoring
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MLOps monitoring: ingestion, training, live drift.")
    parser.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit 1 if any drift threshold is breached",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print full report JSON to stdout",
    )
    parser.add_argument(
        "--pushgateway-url",
        default="",
        help="Prometheus Pushgateway URL. Defaults to MLOPS_PROMETHEUS_PUSHGATEWAY_URL.",
    )
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from mlops_data.pipelines.monitoring import MonitoringConfig, run_monitoring

    if os.environ.get("MLOPS_MONITOR_SYNC_S3", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            sync_monitoring_inputs_from_s3()
        except Exception as e:
            print(f"warning: failed to sync monitoring inputs from S3: {e}", file=sys.stderr)

    try:
        report = run_monitoring(config=MonitoringConfig.from_env())
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if os.environ.get("MLOPS_MONITOR_UPLOAD_S3_PREFIX", "").strip():
        try:
            upload_monitoring_outputs_to_s3(report)
        except Exception as e:
            print(f"warning: failed to upload monitoring outputs to S3: {e}", file=sys.stderr)

    pushgateway_url = args.pushgateway_url or os.environ.get("MLOPS_PROMETHEUS_PUSHGATEWAY_URL", "")
    if pushgateway_url.strip():
        try:
            push_monitoring_metrics(report, pushgateway_url.strip())
        except Exception as e:
            print(f"warning: failed to push Prometheus metrics: {e}", file=sys.stderr)

    if args.print_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Monitoring run OK")
        print(f"  json: {report.get('output_json')}")
        if report.get("output_parquet"):
            print(f"  parquet: {report.get('output_parquet')}")
        print(f"  any_breach: {report.get('any_breach')}")
        for b in (report.get("drift") or {}).get("breaches") or []:
            if b.get("breached"):
                print(f"  BREACH {b.get('metric')}: {b}")

    if args.fail_on_breach and report.get("any_breach"):
        return 1
    return 0


def _num(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def push_monitoring_metrics(report: dict[str, object], pushgateway_url: str) -> None:
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

    registry = CollectorRegistry()
    any_breach = Gauge("mlops_monitor_any_breach", "Whether latest monitor report has any drift breach.", registry=registry)
    live_feature_rows = Gauge("mlops_monitor_live_feature_rows", "Live feature rows inspected by monitor.", registry=registry)
    live_score_rows = Gauge("mlops_monitor_live_score_rows", "Live score rows inspected by monitor.", registry=registry)
    live_score_mean = Gauge("mlops_monitor_live_score_mean", "Mean live toxicity score in monitor window.", registry=registry)
    breach_metric = Gauge("mlops_monitor_breach", "Per-drift-check breach flag.", ["metric"], registry=registry)

    any_breach.set(1.0 if report.get("any_breach") else 0.0)
    live = report.get("live") if isinstance(report.get("live"), dict) else {}
    live_feature_rows.set(_num(live.get("feature_rows") if isinstance(live, dict) else 0))
    live_score_rows.set(_num(live.get("score_rows") if isinstance(live, dict) else 0))
    score_distribution = live.get("score_distribution") if isinstance(live, dict) else {}
    if isinstance(score_distribution, dict):
        live_score_mean.set(_num(score_distribution.get("mean")))

    drift = report.get("drift") if isinstance(report.get("drift"), dict) else {}
    breaches = drift.get("breaches", []) if isinstance(drift, dict) else []
    if isinstance(breaches, list):
        for b in breaches:
            if isinstance(b, dict):
                breach_metric.labels(metric=str(b.get("metric", "unknown"))).set(1.0 if b.get("breached") else 0.0)

    push_to_gateway(pushgateway_url, job="mlops_drift_monitor", registry=registry)


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("MLOPS_S3_ENDPOINT") or None,
        aws_access_key_id=os.environ.get("MLOPS_S3_ACCESS_KEY") or None,
        aws_secret_access_key=os.environ.get("MLOPS_S3_SECRET_KEY") or None,
        region_name=os.environ.get("MLOPS_S3_REGION") or "us-east-1",
    )


def sync_monitoring_inputs_from_s3() -> None:
    bucket = os.environ.get("MLOPS_S3_BUCKET", "moderation-data")
    prefix = os.environ.get("MLOPS_MONITOR_S3_PREFIX", "mlmoderation").strip().strip("/")
    downloads = {
        f"{prefix}/logs/online_features_v1.jsonl": os.environ.get(
            "MLOPS_MONITOR_LIVE_FEATURES_JSONL",
            "/work/data/mlmoderation/logs/online_features_v1.jsonl",
        ),
        f"{prefix}/logs/online_scores_v1.jsonl": os.environ.get(
            "MLOPS_MONITOR_LIVE_SCORES_JSONL",
            "/work/data/mlmoderation/logs/online_scores_v1.jsonl",
        ),
        f"{prefix}/feedback/moderation_feedback_v2.jsonl": os.environ.get(
            "MLOPS_MONITOR_LIVE_FEEDBACK_JSONL",
            "/work/data/mlmoderation/feedback/moderation_feedback_v2.jsonl",
        ),
    }
    client = _s3_client()
    for key, dst in downloads.items():
        path = Path(dst)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.download_file(bucket, key, str(path))
        except Exception as e:
            print(f"warning: could not download s3://{bucket}/{key}: {e}", file=sys.stderr)


def upload_monitoring_outputs_to_s3(report: dict[str, object]) -> None:
    bucket = os.environ.get("MLOPS_S3_BUCKET", "moderation-data")
    prefix = os.environ["MLOPS_MONITOR_UPLOAD_S3_PREFIX"].strip().strip("/")
    client = _s3_client()
    for field in ("output_json", "output_parquet"):
        value = report.get(field)
        if not value:
            continue
        path = Path(str(value))
        if not path.is_file():
            continue
        key = f"{prefix}/{path.name}"
        client.upload_file(str(path), bucket, key)
        print(f"uploaded s3://{bucket}/{key}")


if __name__ == "__main__":
    raise SystemExit(main())
