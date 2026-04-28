from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((p / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _client():
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


def load_events(local_path: str = "serving/logs/inference_events.jsonl", use_minio: bool = False, backend: str | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if use_minio:
        bucket = os.environ.get("MONITORING_S3_BUCKET", "mlops-monitoring")
        prefix = os.environ.get("MONITORING_S3_KEY_PREFIX", "logs") + "/inference_events_"
        try:
            client = _client()
            listed = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            for obj in listed.get("Contents", []):
                body = client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read().decode("utf-8")
                for line in body.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if backend and row.get("backend") != backend:
                        continue
                    events.append(row)
        except Exception:
            return []
    else:
        p = Path(local_path)
        if not p.exists():
            return []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if backend and row.get("backend") != backend:
                continue
            events.append(row)
    return events


def compute_metrics(events: list[dict[str, Any]]) -> dict[str, float]:
    if not events:
        return {
            "total_requests": 0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "error_rate": 0.0,
            "rps": 0.0,
        }

    latencies = [float(e.get("latency_ms", 0.0)) for e in events]
    total = len(events)
    errors = sum(1 for e in events if not bool(e.get("success", False)))

    times = sorted(_parse_ts(e["timestamp"]) for e in events if e.get("timestamp"))
    if len(times) >= 2:
        span = max((times[-1] - times[0]).total_seconds(), 1e-6)
        rps = total / span
    else:
        rps = float(total)

    return {
        "total_requests": total,
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "p99_latency_ms": _percentile(latencies, 99),
        "error_rate": errors / total,
        "rps": rps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute serving metrics from inference JSONL events")
    parser.add_argument("--local-log", default="serving/logs/inference_events.jsonl")
    parser.add_argument("--from-minio", action="store_true")
    parser.add_argument("--backend", choices=["fastapi", "ray"], default=None)
    args = parser.parse_args()

    events = load_events(local_path=args.local_log, use_minio=args.from_minio, backend=args.backend)
    print(json.dumps(compute_metrics(events), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
