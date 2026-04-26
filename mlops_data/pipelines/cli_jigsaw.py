"""
CLI entrypoint: ``python -m mlops_data.pipelines.cli_jigsaw`` from repository root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest Jigsaw CSVs to binary parquet + manifest (local + optional S3/MinIO)."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("."),
        help="Directory containing train.csv, test.csv, test_labels.csv (default: cwd)",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy CSVs; use files already under MLOPS local jigsaw raw dir",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip S3/MinIO upload (local artifacts only)",
    )
    parser.add_argument(
        "--no-local-write",
        action="store_true",
        help="Skip writing parquet/manifest under local artifacts tree",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from mlops_data.pipelines.jigsaw_ingestion import run_jigsaw_ingestion

    try:
        result = run_jigsaw_ingestion(
            source_csv_dir=args.source_dir if not args.no_copy else None,
            copy_sources=not args.no_copy,
            upload_object_storage=not args.no_upload,
            write_local=not args.no_local_write,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("Jigsaw ingestion OK")
    print(f"  rows: {result.row_count}")
    print(f"  label distribution: {result.quality_report.get('label_distribution')}")
    print(f"  local parquet: {result.local_parquet_path}")
    print(f"  local manifest: {result.local_manifest_path}")
    print(f"  s3 parquet: {result.parquet_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
