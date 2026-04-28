from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3


def _get_client():
    endpoint = os.environ.get("MONITORING_S3_ENDPOINT_URL", os.environ.get("MLFLOW_S3_ENDPOINT_URL", "http://minio.platform.svc.cluster.local:9000"))
    access_key = os.environ.get("MONITORING_AWS_ACCESS_KEY_ID", os.environ.get("AWS_ACCESS_KEY_ID", ""))
    secret_key = os.environ.get("MONITORING_AWS_SECRET_ACCESS_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY", ""))
    region = os.environ.get("MONITORING_AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def main() -> None:
    local_path = Path(os.environ.get("INFERENCE_EVENTS_LOG_PATH", "serving/logs/inference_events.jsonl"))
    bucket = os.environ.get("MONITORING_S3_BUCKET", "mlops-monitoring")
    key_prefix = os.environ.get("MONITORING_S3_KEY_PREFIX", "logs")
    interval_sec = int(os.environ.get("MONITORING_UPLOAD_INTERVAL_SEC", "15"))

    client = _get_client()
    try:
        client.create_bucket(Bucket=bucket)
    except Exception:
        # Bucket may already exist or be owned by another call path.
        pass

    last_uploaded_mtime = 0.0
    while True:
        try:
            if local_path.exists():
                mtime = local_path.stat().st_mtime
                if mtime > last_uploaded_mtime and local_path.stat().st_size > 0:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    key = f"{key_prefix}/inference_events_{ts}.jsonl"
                    client.upload_file(str(local_path), bucket, key)
                    last_uploaded_mtime = mtime
                    print(f"uploaded s3://{bucket}/{key}")
        except Exception as exc:
            print(f"upload_error: {exc}")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
