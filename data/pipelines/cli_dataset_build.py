"""
CLI: ``python -m data.pipelines.cli_dataset_build`` from repository root.

Reads ``labeled_messages.parquet`` from integrated paths (see ``dataset_build`` module).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build train/val/eval parquet + manifest + quality_report from labeled data."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if quality_report.ok is false",
    )
    parser.add_argument(
        "--dry-print-config",
        action="store_true",
        help="Print DatasetBuildConfig from environment and exit",
    )
    parser.add_argument(
        "--no-fail-on-quality",
        action="store_true",
        help="Do not abort the build when quality_report.ok is false (dev only; still writes diagnostics)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from data.pipelines.dataset_build import DatasetBuildConfig, run_dataset_build

    cfg = DatasetBuildConfig.from_env()
    if args.no_fail_on_quality:
        cfg.fail_on_quality_error = False
    if args.dry_print_config:
        print(json.dumps(cfg.__dict__, default=str, indent=2))
        return 0

    try:
        result = run_dataset_build(config=cfg)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("Dataset build finished")
    print(f"  train: {result.row_counts['train']} rows -> {result.train_path}")
    print(f"  val:   {result.row_counts['val']} rows -> {result.val_path}")
    print(f"  eval:  {result.row_counts['eval']} rows -> {result.eval_path}")
    print(f"  manifest: {result.manifest_path}")
    print(f"  lineage:  {result.lineage_path}")
    print(f"  quality:  {result.quality_report_path} (ok={result.quality_report.get('ok')})")

    if args.strict and not result.quality_report.get("ok", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
