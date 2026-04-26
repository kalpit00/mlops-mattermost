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
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from mlops_data.pipelines.monitoring import MonitoringConfig, run_monitoring

    try:
        report = run_monitoring(config=MonitoringConfig.from_env())
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

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


if __name__ == "__main__":
    raise SystemExit(main())
