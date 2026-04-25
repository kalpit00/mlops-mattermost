"""
Jigsaw toxicity CSV ingest to binary schema, local artifacts, and object storage.

Integrated system (short README)
--------------------------------
**Role:** Landing job for external Jigsaw CSV dumps. Writes mirrored copies under the
shared object-storage layout used elsewhere in this repo (``moderation-data`` bucket,
``raw/jigsaw/*`` and ``transformed/jigsaw/*`` keys — overridable via env). Local
staging defaults to ``data/artifacts/jigsaw/`` under the current working directory
(typically repo root) so paths align with ``docker-compose-data.yml`` host mounts
when you point ``MLOPS_LOCAL_ARTIFACTS_ROOT`` at the same tree.

**Run (CLI):** from repository root, with deps installed (``boto3``, ``pandas``,
``pyarrow`` or ``fastparquet``)::

    python -m data.pipelines.cli_jigsaw --source-dir ./path/to/csvs

**Run (library):** ``from data.pipelines import run_jigsaw_ingestion`` (requires
``PYTHONPATH`` including the repo root, or an installed package layout)::

    from pathlib import Path
    from data.pipelines import run_jigsaw_ingestion

    run_jigsaw_ingestion(source_csv_dir=Path("./train_csvs"))

**Env:** ``MLOPS_S3_*`` and ``MLOPS_JIGSAW_*`` — see ``JigsawIngestionConfig.from_env``.
Object uploads are skipped if ``MLOPS_SKIP_S3_UPLOAD=1`` (optional safety for local-only runs).
"""

from __future__ import annotations

import io
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from pandas.api import types as pdt

TOXIC_COLUMNS = [
    "toxic",
    "severe_toxic",
    "obscene",
    "threat",
    "insult",
    "identity_hate",
]

REQUIRED_TRAIN_COLUMNS = ["id", "comment_text", *TOXIC_COLUMNS]
REQUIRED_RAW_FILES = ("train.csv", "test.csv", "test_labels.csv")

OUTPUT_COLUMNS = ("example_id", "text", "label_toxic", "label_source", "created_at")


class JigsawIngestionError(Exception):
    """Raised when validation or IO fails before a successful ingest."""


@dataclass
class JigsawIngestionConfig:
    """Configuration loaded from environment variables with optional overrides."""

    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = "admin"
    s3_secret_key: str = "admin12345"
    bucket: str = "moderation-data"
    s3_region: str = "us-east-1"
    raw_prefix: str = "raw/jigsaw"
    transformed_prefix: str = "transformed/jigsaw"
    local_artifacts_root: Path = field(default_factory=lambda: Path("data/artifacts"))
    min_rows: int = 1
    parquet_engine: str = "auto"
    skip_s3_upload: bool = False

    @property
    def local_raw_dir(self) -> Path:
        return self.local_artifacts_root / "jigsaw" / "raw"

    @property
    def local_transformed_dir(self) -> Path:
        return self.local_artifacts_root / "jigsaw" / "transformed"

    @property
    def local_parquet_path(self) -> Path:
        return self.local_transformed_dir / "comments_binary.parquet"

    @property
    def local_manifest_path(self) -> Path:
        return self.local_transformed_dir / "manifest.json"

    @classmethod
    def from_env(cls, **overrides: Any) -> JigsawIngestionConfig:
        def _b(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        def _i(name: str, default: int) -> int:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return int(v)

        _lar = os.environ.get("MLOPS_LOCAL_ARTIFACTS_ROOT")
        if _lar is None or not str(_lar).strip():
            _lar = "data/artifacts"
        root = Path(_lar).expanduser()

        cfg = cls(
            s3_endpoint=os.environ.get("MLOPS_S3_ENDPOINT", "http://127.0.0.1:9000"),
            s3_access_key=os.environ.get("MLOPS_S3_ACCESS_KEY", "admin"),
            s3_secret_key=os.environ.get("MLOPS_S3_SECRET_KEY", "admin12345"),
            bucket=os.environ.get("MLOPS_S3_BUCKET", "moderation-data"),
            s3_region=os.environ.get("MLOPS_S3_REGION", "us-east-1"),
            raw_prefix=os.environ.get("MLOPS_JIGSAW_RAW_PREFIX", "raw/jigsaw").strip(
                "/"
            ),
            transformed_prefix=os.environ.get(
                "MLOPS_JIGSAW_TRANSFORMED_PREFIX", "transformed/jigsaw"
            ).strip("/"),
            local_artifacts_root=root,
            min_rows=_i("MLOPS_JIGSAW_MIN_ROWS", 1),
            parquet_engine=os.environ.get("MLOPS_PARQUET_ENGINE", "auto").lower(),
            skip_s3_upload=_b("MLOPS_SKIP_S3_UPLOAD", False),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                if k == "local_artifacts_root":
                    setattr(cfg, k, Path(v).expanduser())
                else:
                    setattr(cfg, k, v)
        return cfg


@dataclass
class JigsawIngestionResult:
    row_count: int
    manifest: dict[str, Any]
    quality_report: dict[str, Any]
    parquet_uri: str
    manifest_uri: str
    local_parquet_path: Path
    local_manifest_path: Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_s3_client(cfg: JigsawIngestionConfig):
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name=cfg.s3_region,
    )


def _upload_bytes(
    s3, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def _upload_dataframe_csv(s3, bucket: str, df: pd.DataFrame, key: str) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    _upload_bytes(s3, bucket, key, buf.getvalue().encode("utf-8"), "text/csv")


def _upload_dataframe_parquet(
    s3, bucket: str, df: pd.DataFrame, key: str, engine: str
) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine=engine)
    _upload_bytes(
        s3, bucket, key, buf.getvalue(), content_type="application/octet-stream"
    )


def _resolve_parquet_engine(preferred: str) -> str:
    if preferred == "pyarrow":
        return "pyarrow"
    if preferred == "fastparquet":
        return "fastparquet"
    try:
        import pyarrow  # noqa: F401

        return "pyarrow"
    except ImportError:
        pass
    try:
        import fastparquet  # noqa: F401

        return "fastparquet"
    except ImportError as e:
        raise JigsawIngestionError(
            "Install pyarrow or fastparquet to write parquet."
        ) from e


def copy_uploaded_csvs(source_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fname in REQUIRED_RAW_FILES:
        src = source_dir / fname
        dst = dest_dir / fname
        if not src.is_file():
            raise JigsawIngestionError(f"Missing required file: {src.resolve()}")
        shutil.copy2(src, dst)


def load_raw_data(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = pd.read_csv(raw_dir / "train.csv")
    test_df = pd.read_csv(raw_dir / "test.csv")
    test_labels_df = pd.read_csv(raw_dir / "test_labels.csv")
    return train_df, test_df, test_labels_df


def validate_train_schema(train_df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_TRAIN_COLUMNS if c not in train_df.columns]
    if missing:
        raise JigsawIngestionError(
            f"train.csv missing columns: {missing}; required: {REQUIRED_TRAIN_COLUMNS}"
        )


def build_comments_binary(train_df: pd.DataFrame, created_at: str) -> pd.DataFrame:
    train_min_df = train_df.copy()
    train_min_df["label_toxic"] = (
        train_min_df[TOXIC_COLUMNS].fillna(0).sum(axis=1) > 0
    ).astype("int8")

    return pd.DataFrame(
        {
            "example_id": train_min_df["id"].astype(str),
            "text": train_min_df["comment_text"].astype(str),
            "label_toxic": train_min_df["label_toxic"],
            "label_source": "jigsaw_train_rules_v1",
            "created_at": created_at,
        }
    )


def run_output_quality_checks(
    df: pd.DataFrame, min_rows: int
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_ok": False,
        "columns_expected": list(OUTPUT_COLUMNS),
        "null_counts": {},
        "null_violations": [],
        "row_count": len(df),
        "row_count_ok": False,
        "label_distribution": {},
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
    }

    missing_cols = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing_cols:
        report["schema_error"] = f"Missing columns: {missing_cols}"
        return report

    extra = [c for c in df.columns if c not in OUTPUT_COLUMNS]
    if extra:
        report["schema_error"] = f"Unexpected columns: {extra}"
        return report

    report["schema_ok"] = True

    if not pdt.is_integer_dtype(df["label_toxic"]) and not pdt.is_bool_dtype(
        df["label_toxic"]
    ):
        report["dtype_violations"] = [
            f"label_toxic dtype {df['label_toxic'].dtype} is not integer-like"
        ]
    else:
        report["dtype_violations"] = []

    nulls = df[list(OUTPUT_COLUMNS)].isna().sum()
    report["null_counts"] = nulls.astype(int).to_dict()

    for col in ("example_id", "text", "label_toxic"):
        if nulls[col] > 0:
            report["null_violations"].append(f"{col} has {int(nulls[col])} nulls")

    report["row_count_ok"] = len(df) >= min_rows
    vc = df["label_toxic"].value_counts(dropna=False)
    report["label_distribution"] = {str(k): int(v) for k, v in vc.items()}

    return report


def assert_quality_ok(report: dict[str, Any], min_rows: int) -> None:
    if not report.get("schema_ok"):
        raise JigsawIngestionError(
            report.get("schema_error", "Output schema validation failed")
        )
    if report.get("dtype_violations"):
        raise JigsawIngestionError("; ".join(report["dtype_violations"]))
    if report.get("null_violations"):
        raise JigsawIngestionError("; ".join(report["null_violations"]))
    if not report.get("row_count_ok"):
        raise JigsawIngestionError(
            f"Row count {report['row_count']} below minimum {min_rows}"
        )


def run_jigsaw_ingestion(
    *,
    source_csv_dir: Optional[Path] = None,
    config: Optional[JigsawIngestionConfig] = None,
    copy_sources: bool = True,
    upload_object_storage: bool = True,
    write_local: bool = True,
) -> JigsawIngestionResult:
    """
    Ingest Jigsaw CSVs from ``source_csv_dir`` into the binary moderation schema,
    run quality checks, write parquet + manifest locally, and optionally upload to S3/MinIO.

    If ``copy_sources`` is False, expects ``train.csv``, ``test.csv``, and
    ``test_labels.csv`` to already exist under ``config.local_raw_dir``.
    """
    cfg = config or JigsawIngestionConfig.from_env()
    if cfg.skip_s3_upload:
        upload_object_storage = False

    created_at = _utc_now_iso()
    parquet_engine = _resolve_parquet_engine(cfg.parquet_engine)

    if copy_sources:
        if source_csv_dir is None:
            raise JigsawIngestionError(
                "source_csv_dir is required when copy_sources=True"
            )
        copy_uploaded_csvs(source_csv_dir, cfg.local_raw_dir)
    else:
        cfg.local_raw_dir.mkdir(parents=True, exist_ok=True)

    train_df, test_df, test_labels_df = load_raw_data(cfg.local_raw_dir)
    validate_train_schema(train_df)

    comments_binary_df = build_comments_binary(train_df, created_at=created_at)
    quality_report = run_output_quality_checks(comments_binary_df, cfg.min_rows)
    assert_quality_ok(quality_report, cfg.min_rows)

    cfg.local_transformed_dir.mkdir(parents=True, exist_ok=True)
    if write_local:
        comments_binary_df.to_parquet(
            cfg.local_parquet_path,
            index=False,
            engine=parquet_engine,
        )

    raw_keys = [
        f"{cfg.raw_prefix}/train.csv",
        f"{cfg.raw_prefix}/test.csv",
        f"{cfg.raw_prefix}/test_labels.csv",
    ]
    parquet_key = f"{cfg.transformed_prefix}/comments_binary.parquet"
    manifest_key = f"{cfg.transformed_prefix}/manifest.json"

    manifest: dict[str, Any] = {
        "dataset_version": "v1",
        "schema_version": "v1",
        "source": "jigsaw",
        "source_type": "external_dataset",
        "input_keys": raw_keys,
        "primary_input_for_output": f"{cfg.raw_prefix}/train.csv",
        "output_key": parquet_key,
        "transform_version": "jigsaw_binary_v1",
        "transform_description": (
            "Converted multi-label Jigsaw toxicity columns into one binary label_toxic field"
        ),
        "label_definition": (
            "label_toxic=1 if any toxicity-related source column is positive, else 0"
        ),
        "rows": int(len(comments_binary_df)),
        "created_at_field_policy": (
            "created_at is pipeline generation time, not original source event time"
        ),
        "generated_at": created_at,
        "quality": quality_report,
    }

    if write_local:
        cfg.local_manifest_path.write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    if upload_object_storage:
        s3 = _make_s3_client(cfg)
        _upload_dataframe_csv(s3, cfg.bucket, train_df, raw_keys[0])
        _upload_dataframe_csv(s3, cfg.bucket, test_df, raw_keys[1])
        _upload_dataframe_csv(s3, cfg.bucket, test_labels_df, raw_keys[2])
        _upload_dataframe_parquet(
            s3, cfg.bucket, comments_binary_df, parquet_key, parquet_engine
        )
        _upload_bytes(
            s3,
            cfg.bucket,
            manifest_key,
            json.dumps(manifest, indent=2).encode("utf-8"),
            "application/json",
        )

    return JigsawIngestionResult(
        row_count=len(comments_binary_df),
        manifest=manifest,
        quality_report=quality_report,
        parquet_uri=f"s3://{cfg.bucket}/{parquet_key}",
        manifest_uri=f"s3://{cfg.bucket}/{manifest_key}",
        local_parquet_path=cfg.local_parquet_path,
        local_manifest_path=cfg.local_manifest_path,
    )
