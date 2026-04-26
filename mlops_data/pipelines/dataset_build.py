"""
Retraining dataset builder: time-ordered, thread-safe splits from labeled production-style data.

**Inputs (integrated paths)**
- Local glob (default): ``data/artifacts/synthetic/nightly/*/labeled_messages.parquet``
  from :mod:`mlops_data.pipelines.synthetic_messages`.
- Optional MinIO/S3: set ``MLOPS_S3_*`` and ``MLOPS_DATASET_SOURCE_PREFIX`` (e.g. ``nightly/``).
- Optional moderator JSONL (``moderation_feedback_v1`` from the server): ``MLOPS_DATASET_FEEDBACK_GLOB``.

**Training rows**
- Does **not** include online inference scores (``toxicity_score``, ``model_version``, etc.).
- ``prior_violation_count`` is computed **per split** and **causally** within time order so
  val/eval threads do not contribute to train priors (avoids user-level leakage across splits).

**Outputs**
- ``train.parquet``, ``val.parquet``, ``eval.parquet``, ``manifest.json``,
  ``quality_report.json``, ``training_lineage.json`` (input hashes + config snapshot; no raw text)
  under ``MLOPS_DATASET_OUTPUT_ROOT`` / ``datasets/{dataset_date}/``.
- Failed quality (when ``MLOPS_DATASET_FAIL_ON_QUALITY`` is true): writes diagnostics only,
  no training parquet export.

**CLI:** ``python -m mlops_data.pipelines.cli_dataset_build``
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# Columns that must never appear in exported training features (inference / scores).
INFERENCE_LEAKAGE_COLUMNS = frozenset(
    {
        "toxicity_score",
        "inference_score",
        "score",
        "pred_score",
        "model_score",
        "pred_label",
        "predicted_label",
        "queue_priority",
        "model_version",
        "scored_at",
        "feature_row_schema",
        "feature_version",
        "schema_version",  # score row schema; keep out of training matrix
    }
)

TRAINING_EXPORT_COLUMNS = [
    "example_id",
    "message_id",
    "thread_id",
    "text",
    "channel_type",
    "prior_violation_count",
    "final_label_toxic",
    "label_source",
    "event_time",
]

# Never persist raw user handles, reviewer ids, or network identifiers in training parquet.
PRIVACY_STRIP_COLUMNS = frozenset(
    {
        "user_id",
        "mattermost_user_id",
        "synthetic_user_id",
        "username",
        "author_username",
        "email",
        "ip_address",
        "client_ip",
        "feedback_reviewer_user_id",
        "reviewer_user_id",
        "author_id",
        "props",
    }
)

QUALITY_REPORT_SCHEMA_VERSION = "dataset_quality_v2"
MANIFEST_SCHEMA_VERSION = "dataset_manifest_v2"
TRAINING_ROW_SCHEMA_VERSION = "moderation_train_row_v1"


class DatasetBuildError(Exception):
    pass


@dataclass
class DatasetBuildConfig:
    dataset_date: str = ""  # default: min date seen or today
    include_ambiguous: bool = True
    ambiguous_fraction: float = 0.15
    train_frac: float = 0.70
    val_frac: float = 0.15
    eval_frac: float = 0.15
    random_seed: int = 42
    local_source_glob: str = "data/artifacts/synthetic/nightly/*/labeled_messages.parquet"
    output_root: Path = field(default_factory=lambda: Path("data/artifacts"))
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_source_prefix: str = ""  # e.g. nightly/ — if set, pull parquet from S3 instead of glob
    s3_output_prefix: str = ""  # if set, upload outputs to S3 under datasets/{date}/
    skip_s3_upload: bool = False
    dataset_version: str = "v1"
    schema_version: str = "v1"
    feedback_glob: str = ""  # e.g. data/mlmoderation/feedback/moderation_feedback_v1.jsonl
    fail_on_quality_error: bool = True
    min_rows_train: int = 50
    min_rows_val: int = 10
    min_rows_eval: int = 20
    eval_minority_min_frac: float = 0.05
    max_text_null_or_empty_frac: float = 0.05
    fairness_slice_columns: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, **overrides: Any) -> DatasetBuildConfig:
        def _b(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return float(v)

        def _i(name: str, default: int) -> int:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return int(v)

        def _slice_cols() -> tuple[str, ...]:
            raw = os.environ.get("MLOPS_DATASET_FAIRNESS_SLICES", "").strip()
            if not raw:
                return ()
            return tuple(c.strip() for c in raw.split(",") if c.strip())

        _dor = os.environ.get("MLOPS_DATASET_OUTPUT_ROOT")
        if _dor is None or not str(_dor).strip():
            _dor = "data/artifacts"
        root = Path(_dor).expanduser()

        _glob = os.environ.get("MLOPS_DATASET_LOCAL_GLOB")
        if _glob is None or not str(_glob).strip():
            _glob = "data/artifacts/synthetic/nightly/*/labeled_messages.parquet"

        cfg = cls(
            dataset_date=os.environ.get("MLOPS_DATASET_DATE", "").strip(),
            include_ambiguous=_b("MLOPS_DATASET_INCLUDE_AMBIGUOUS", True),
            ambiguous_fraction=_f("MLOPS_DATASET_AMBIGUOUS_FRACTION", 0.15),
            train_frac=_f("MLOPS_DATASET_TRAIN_FRAC", 0.70),
            val_frac=_f("MLOPS_DATASET_VAL_FRAC", 0.15),
            eval_frac=_f("MLOPS_DATASET_EVAL_FRAC", 0.15),
            random_seed=int(os.environ.get("MLOPS_DATASET_SEED", "42")),
            local_source_glob=_glob,
            output_root=root,
            s3_bucket=os.environ.get("MLOPS_S3_BUCKET", ""),
            s3_endpoint=os.environ.get("MLOPS_S3_ENDPOINT", ""),
            s3_access_key=os.environ.get("MLOPS_S3_ACCESS_KEY", ""),
            s3_secret_key=os.environ.get("MLOPS_S3_SECRET_KEY", ""),
            s3_region=os.environ.get("MLOPS_S3_REGION", "us-east-1"),
            s3_source_prefix=os.environ.get("MLOPS_DATASET_S3_SOURCE_PREFIX", "").strip(),
            s3_output_prefix=os.environ.get("MLOPS_DATASET_S3_OUTPUT_PREFIX", "").strip(),
            skip_s3_upload=_b("MLOPS_DATASET_SKIP_S3_UPLOAD", False)
            or _b("MLOPS_SKIP_S3_UPLOAD", False),
            dataset_version=os.environ.get("MLOPS_DATASET_VERSION", "v1"),
            schema_version=os.environ.get("MLOPS_DATASET_SCHEMA_VERSION", "v1"),
            feedback_glob=os.environ.get("MLOPS_DATASET_FEEDBACK_GLOB", "").strip(),
            fail_on_quality_error=_b("MLOPS_DATASET_FAIL_ON_QUALITY", True),
            min_rows_train=_i("MLOPS_DATASET_MIN_ROWS_TRAIN", 50),
            min_rows_val=_i("MLOPS_DATASET_MIN_ROWS_VAL", 10),
            min_rows_eval=_i("MLOPS_DATASET_MIN_ROWS_EVAL", 20),
            eval_minority_min_frac=_f("MLOPS_DATASET_EVAL_MINORITY_MIN_FRAC", 0.05),
            max_text_null_or_empty_frac=_f(
                "MLOPS_DATASET_MAX_TEXT_NULL_FRAC", 0.05
            ),
            fairness_slice_columns=_slice_cols(),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                if k == "output_root":
                    setattr(cfg, k, Path(v).expanduser())
                else:
                    setattr(cfg, k, v)
        return cfg


@dataclass
class DatasetBuildResult:
    train_path: Path
    val_path: Path
    eval_path: Path
    manifest_path: Path
    quality_report_path: Path
    lineage_path: Path
    manifest: dict[str, Any]
    quality_report: dict[str, Any]
    row_counts: dict[str, int]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _label_minority_fraction(counts: dict[str, int]) -> float | None:
    if not counts:
        return None
    total = sum(int(v) for v in counts.values())
    if total <= 0:
        return None
    return min(int(v) / total for v in counts.values())


def build_fairness_slice_report(
    eval_df: pd.DataFrame,
    slice_columns: tuple[str, ...],
) -> dict[str, Any]:
    """Placeholder + optional eval slice x label counts when columns exist."""
    base: dict[str, Any] = {
        "schema_version": "fairness_slice_report_v0",
        "slices_requested": list(slice_columns),
        "status": "placeholder",
        "eval_slice_label_counts": {},
        "notes": (
            "Populate with offline slice metrics / thresholds when protected or proxy "
            "attributes exist; use MLOPS_DATASET_FAIRNESS_SLICES for coarse buckets."
        ),
    }
    if not slice_columns:
        return base
    if len(eval_df) == 0:
        base["status"] = "eval_empty"
        return base
    missing = [c for c in slice_columns if c not in eval_df.columns]
    if missing:
        base["status"] = "slices_missing_in_eval"
        base["missing_columns"] = missing
        return base
    base["status"] = "eval_counts_only"
    out: dict[str, Any] = {}
    for col in slice_columns:
        sub = eval_df[[col, "final_label_toxic"]].copy()
        sub[col] = sub[col].astype(str)
        ct = pd.crosstab(sub[col], sub["final_label_toxic"])
        out[str(col)] = ct.astype(int).to_dict()
    base["eval_slice_label_counts"] = out
    return base


def map_label_toxic(x: Any) -> float:
    s = str(x).strip().lower()
    if s in ("toxic", "tox", "1", "true"):
        return 1.0
    if s in (
        "non_toxic",
        "non-toxic",
        "nontoxic",
        "safe",
        "clean",
        "0",
        "false",
    ):
        return 0.0
    return np.nan


def normalize_labeled_frame(df: pd.DataFrame, source_key: str) -> pd.DataFrame:
    """Map synthetic / API-shaped columns to the batch builder's canonical names."""
    out = df.copy()
    out["_source_key"] = source_key

    # message id
    if "message_id" not in out.columns:
        for c in ("mattermost_post_id", "event_id", "id"):
            if c in out.columns:
                out["message_id"] = out[c].astype(str)
                break
    else:
        out["message_id"] = out["message_id"].astype(str)

    if "message_id" not in out.columns:
        raise DatasetBuildError(
            f"Could not resolve message_id from columns: {list(out.columns)}"
        )

    # thread id
    if "thread_id" not in out.columns:
        if "synthetic_thread_id" in out.columns:
            out["thread_id"] = out["synthetic_thread_id"].astype(str)
        else:
            raise DatasetBuildError("Missing thread_id / synthetic_thread_id")

    # text
    if "message_text" not in out.columns:
        if "message" in out.columns:
            out["message_text"] = out["message"].astype(str)
        elif "text" in out.columns:
            out["message_text"] = out["text"].astype(str)
        else:
            raise DatasetBuildError("Missing message_text / message / text")

    # timestamp
    if "created_at" in out.columns:
        out["event_time"] = pd.to_datetime(out["created_at"], errors="coerce", utc=True)
    elif "create_at" in out.columns:
        out["event_time"] = pd.to_datetime(
            out["create_at"], unit="ms", errors="coerce", utc=True
        )
    elif "event_time" in out.columns:
        out["event_time"] = pd.to_datetime(out["event_time"], errors="coerce", utc=True)
    else:
        raise DatasetBuildError("Missing created_at / create_at / event_time")

    if "user_hash" not in out.columns:
        if "synthetic_user_id" in out.columns:
            import hashlib

            def _h(uid: str) -> str:
                return hashlib.sha256(str(uid).encode()).hexdigest()[:16]

            out["user_hash"] = out["synthetic_user_id"].astype(str).map(_h)
        else:
            out["user_hash"] = ""

    if "channel_type" not in out.columns:
        out["channel_type"] = "unknown"

    if "reviewed" not in out.columns:
        out["reviewed"] = True

    if "moderation_label" not in out.columns:
        raise DatasetBuildError("Missing moderation_label")

    return out


def _discover_glob_paths(glob_pattern: str) -> list[Path]:
    roots = [Path.cwd(), *list(Path.cwd().parents)[:6]]
    seen: set[Path] = set()
    paths: list[Path] = []
    for root in roots:
        for p in root.glob(glob_pattern):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                paths.append(p)
    return sorted(paths, key=lambda x: str(x))


def load_local_labeled_frames(glob_pattern: str) -> tuple[pd.DataFrame, list[str]]:
    paths = _discover_glob_paths(glob_pattern)
    if not paths:
        raise DatasetBuildError(f"No files matched glob: {glob_pattern}")
    dfs = []
    keys = []
    for p in paths:
        dfs.append(normalize_labeled_frame(pd.read_parquet(p), str(p.resolve())))
        keys.append(str(p.resolve()))
    return pd.concat(dfs, ignore_index=True), keys


FEEDBACK_ROW_SCHEMA = "moderation_feedback_v1"


def load_moderation_feedback_jsonl(paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("schema_version") != FEEDBACK_ROW_SCHEMA:
                continue
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def discover_feedback_paths(glob_pattern: str) -> list[Path]:
    if not glob_pattern.strip():
        return []
    return _discover_glob_paths(glob_pattern)


def apply_moderation_feedback_overlay(
    df: pd.DataFrame, feedback: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Latest feedback row per message_id wins; sets moderation_label + reviewed=True."""
    meta: dict[str, Any] = {"feedback_rows_loaded": len(feedback), "rows_updated": 0}
    if feedback is None or len(feedback) == 0:
        return df, meta
    need = {"message_id", "moderation_label", "reviewed_at"}
    if not need.issubset(set(feedback.columns)):
        return df, meta

    fb = feedback.copy()
    fb["message_id"] = fb["message_id"].astype(str)
    fb = fb.sort_values("reviewed_at")
    fb = fb.drop_duplicates(subset=["message_id"], keep="last")

    out = df.copy()
    if "message_id" not in out.columns:
        return out, meta
    out["message_id"] = out["message_id"].astype(str)

    extra = ["moderation_label", "reviewer_user_id", "model_version", "source", "action"]
    cols = ["message_id"] + [c for c in extra if c in fb.columns]
    sub = fb[cols].rename(
        columns={
            "moderation_label": "moderation_label_fb",
            "reviewer_user_id": "feedback_reviewer_user_id",
            "model_version": "feedback_model_version",
            "source": "feedback_source",
            "action": "feedback_action",
        }
    )
    merged = out.merge(sub, on="message_id", how="left")
    mask = merged["moderation_label_fb"].notna()
    meta["rows_updated"] = int(mask.sum())
    merged.loc[mask, "moderation_label"] = merged.loc[mask, "moderation_label_fb"]
    merged.loc[mask, "reviewed"] = True
    merged = merged.drop(columns=["moderation_label_fb"], errors="ignore")
    return merged, meta


def _make_s3_client(cfg: DatasetBuildConfig):
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint or None,
        aws_access_key_id=cfg.s3_access_key or None,
        aws_secret_access_key=cfg.s3_secret_key or None,
        config=Config(signature_version="s3v4"),
        region_name=cfg.s3_region,
    )


def load_s3_labeled_frames(cfg: DatasetBuildConfig) -> tuple[pd.DataFrame, list[str]]:
    import io

    client = _make_s3_client(cfg)
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=cfg.s3_bucket, Prefix=cfg.s3_source_prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith("labeled_messages.parquet") and "online_features" not in k:
                keys.append(k)
    keys = sorted(keys)
    if not keys:
        raise DatasetBuildError(
            f"No labeled_messages.parquet under s3://{cfg.s3_bucket}/{cfg.s3_source_prefix}"
        )
    dfs = []
    for k in keys:
        bio = io.BytesIO()
        obj = client.get_object(Bucket=cfg.s3_bucket, Key=k)
        bio.write(obj["Body"].read())
        bio.seek(0)
        dfs.append(normalize_labeled_frame(pd.read_parquet(bio), k))
    return pd.concat(dfs, ignore_index=True), keys


def filter_candidates(
    df: pd.DataFrame, cfg: DatasetBuildConfig
) -> pd.DataFrame:
    d = df.copy()
    if d["reviewed"].dtype != bool:
        d["reviewed"] = d["reviewed"].astype(str).str.lower().isin(
            ("1", "true", "yes")
        )
    d = d[d["reviewed"]].copy()
    d = d.dropna(subset=["message_id", "thread_id", "message_text", "event_time"])

    d["moderation_label"] = d["moderation_label"].astype(str).str.strip().str.lower()
    non_amb = d[d["moderation_label"] != "ambiguous"].copy()
    if cfg.include_ambiguous:
        amb = d[d["moderation_label"] == "ambiguous"].copy()
        if len(amb) > 0:
            amb = amb.sample(frac=cfg.ambiguous_fraction, random_state=cfg.random_seed)
        d = pd.concat([non_amb, amb], ignore_index=True)
    else:
        d = non_amb

    return d.sort_values(
        ["event_time", "thread_id", "message_id"]
    ).reset_index(drop=True)


def build_training_frame(
    candidate_df: pd.DataFrame, split_series: pd.Series
) -> pd.DataFrame:
    """Attach split, compute split-safe causal prior_violation_count, export columns."""
    work = candidate_df.copy()
    work["split"] = split_series.values
    work["final_label_toxic"] = work["moderation_label"].map(map_label_toxic)
    work = work.dropna(subset=["final_label_toxic"]).copy()
    work["final_label_toxic"] = work["final_label_toxic"].astype(int)

    work["is_reviewed_toxic"] = (
        work["moderation_label"].astype(str).str.strip().str.lower() == "toxic"
    ).astype(int)

    work = work.sort_values(
        ["split", "user_hash", "event_time", "message_id"]
    ).reset_index(drop=True)
    work["prior_violation_count"] = work.groupby(
        ["split", "user_hash"], sort=False
    )["is_reviewed_toxic"].cumsum() - work["is_reviewed_toxic"]

    work["example_id"] = work["message_id"].astype(str)
    work["text"] = work["message_text"].astype(str)
    work["label_source"] = "moderator_review"

    drop_priv = [c for c in PRIVACY_STRIP_COLUMNS if c in work.columns]
    if drop_priv:
        work = work.drop(columns=drop_priv, errors="ignore")

    drop_extra = [c for c in INFERENCE_LEAKAGE_COLUMNS if c in work.columns]
    work = work.drop(columns=drop_extra, errors="ignore")
    work = work.drop(columns=["is_reviewed_toxic"], errors="ignore")

    missing = [c for c in TRAINING_EXPORT_COLUMNS if c not in work.columns]
    if missing:
        raise DatasetBuildError(f"Internal error, missing columns: {missing}")

    return work[TRAINING_EXPORT_COLUMNS + ["split"]].copy()


def assign_thread_splits(
    df: pd.DataFrame, cfg: DatasetBuildConfig
) -> pd.Series:
    """Map each row's thread_id -> train|val|eval from thread start times."""
    fr, vf, ef = cfg.train_frac, cfg.val_frac, cfg.eval_frac
    if abs(fr + vf + ef - 1.0) > 1e-6:
        raise DatasetBuildError("train_frac + val_frac + eval_frac must sum to 1.0")

    thread_time = (
        df.groupby("thread_id", as_index=False)["event_time"]
        .min()
        .rename(columns={"event_time": "thread_start_time"})
        .sort_values(["thread_start_time", "thread_id"])
        .reset_index(drop=True)
    )
    n = len(thread_time)
    if n == 0:
        raise DatasetBuildError("No threads after filtering")

    train_cut = int(np.floor(n * fr))
    val_cut = int(np.floor(n * (fr + vf)))

    train_threads = thread_time.iloc[:train_cut]["thread_id"].tolist()
    val_threads = thread_time.iloc[train_cut:val_cut]["thread_id"].tolist()
    eval_threads = thread_time.iloc[val_cut:]["thread_id"].tolist()

    m: dict[str, str] = {}
    m.update({t: "train" for t in train_threads})
    m.update({t: "val" for t in val_threads})
    m.update({t: "eval" for t in eval_threads})
    return df["thread_id"].map(m)


def finalize_split(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["event_time", "thread_id", "message_id"]).reset_index(
        drop=True
    )


def validate_and_report(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    cfg: DatasetBuildConfig,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": QUALITY_REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "ok": True,
        "errors": [],
        "warnings": [],
        "blocking_codes": [],
        "split_row_counts": {
            "train": len(train_df),
            "val": len(val_df),
            "eval": len(eval_df),
        },
        "thresholds": {
            "min_rows_train": cfg.min_rows_train,
            "min_rows_val": cfg.min_rows_val,
            "min_rows_eval": cfg.min_rows_eval,
            "eval_minority_min_frac": cfg.eval_minority_min_frac,
            "max_text_null_or_empty_frac": cfg.max_text_null_or_empty_frac,
        },
        "transparency": {
            "export_columns": list(TRAINING_EXPORT_COLUMNS),
            "training_row_schema_version": TRAINING_ROW_SCHEMA_VERSION,
            "privacy_note": (
                "Exports exclude inference scores, reviewer/user identifiers, and other "
                "PRIVACY_STRIP_COLUMNS; only user_hash-derived priors use hashed ids upstream."
            ),
        },
    }

    def block(code: str, msg: str) -> None:
        report["ok"] = False
        report["errors"].append(msg)
        if code not in report["blocking_codes"]:
            report["blocking_codes"].append(code)

    # split sizes
    total = len(train_df) + len(val_df) + len(eval_df)
    if total == 0:
        block("empty_dataset", "All splits are empty")

    # schema
    for name, part in ("train", train_df), ("val", val_df), ("eval", eval_df):
        missing = [c for c in TRAINING_EXPORT_COLUMNS if c not in part.columns]
        if missing:
            block("schema_missing", f"{name} missing columns: {missing}")
        bad_inf = [c for c in INFERENCE_LEAKAGE_COLUMNS if c in part.columns]
        if bad_inf:
            block("schema_leakage", f"{name} contains forbidden columns: {bad_inf}")
        bad_priv = [c for c in PRIVACY_STRIP_COLUMNS if c in part.columns]
        if bad_priv:
            block("schema_privacy", f"{name} contains disallowed PII columns: {bad_priv}")

    # label balance
    balance: dict[str, Any] = {}
    for name, part in ("train", train_df), ("val", val_df), ("eval", eval_df):
        if "final_label_toxic" in part.columns:
            vc = part["final_label_toxic"].value_counts(dropna=False).to_dict()
            balance[name] = {str(k): int(v) for k, v in vc.items()}
    report["label_balance"] = balance

    eval_bal = balance.get("eval", {})
    eval_min_frac = _label_minority_fraction(eval_bal)
    report["eval_label_minority_fraction"] = eval_min_frac
    if eval_min_frac is not None and eval_min_frac < cfg.eval_minority_min_frac:
        block(
            "eval_label_imbalance",
            f"Eval minority class fraction {eval_min_frac:.4f} below "
            f"threshold {cfg.eval_minority_min_frac}",
        )

    for name, part, minimum in (
        ("train", train_df, cfg.min_rows_train),
        ("val", val_df, cfg.min_rows_val),
        ("eval", eval_df, cfg.min_rows_eval),
    ):
        if len(part) < minimum:
            block(
                "split_too_small",
                f"{name} rows {len(part)} below minimum {minimum}",
            )

    # missing values / empty text
    nulls: dict[str, Any] = {}
    text_empty: dict[str, float] = {}
    for name, part in ("train", train_df), ("val", val_df), ("eval", eval_df):
        nulls[name] = part[TRAINING_EXPORT_COLUMNS].isna().sum().astype(int).to_dict()
        if "text" in part.columns:
            s = part["text"].fillna("").astype(str)
            bad = float((s.str.len() == 0).mean())
            text_empty[name] = round(bad, 6)
            if bad > cfg.max_text_null_or_empty_frac:
                block(
                    "text_empty_rate",
                    f"{name} empty text rate {bad:.4f} above "
                    f"{cfg.max_text_null_or_empty_frac}",
                )
    report["missing_value_counts"] = nulls
    report["text_empty_rate_by_split"] = text_empty

    # thread leakage
    tt, vt, et = (
        set(train_df["thread_id"].astype(str)),
        set(val_df["thread_id"].astype(str)),
        set(eval_df["thread_id"].astype(str)),
    )
    pairs = [
        ("train_val", tt & vt),
        ("train_eval", tt & et),
        ("val_eval", vt & et),
    ]
    leak: dict[str, Any] = {}
    for label, inter in pairs:
        leak[label] = {"intersection_size": len(inter), "sample": list(inter)[:5]}
        if inter:
            block(
                "thread_leakage",
                f"Thread leakage {label}: {len(inter)} overlapping thread_ids",
            )
    report["thread_leakage"] = leak

    fr, vf, ef = cfg.train_frac, cfg.val_frac, cfg.eval_frac
    report["expected_thread_fractions"] = {"train": fr, "val": vf, "eval": ef}

    report["fairness"] = build_fairness_slice_report(
        eval_df, cfg.fairness_slice_columns
    )

    return report


def build_training_lineage(
    *,
    build_id: str,
    dataset_date: str,
    input_keys: list[str],
    cfg: DatasetBuildConfig,
    row_counts: dict[str, int],
) -> dict[str, Any]:
    """Accountability log: which files and hashes fed this build (no raw message text)."""
    inputs: list[dict[str, Any]] = []
    for key in input_keys:
        p = Path(key)
        rec: dict[str, Any] = {"path_or_key": key, "kind": "local" if p.is_file() else "uri"}
        if p.is_file():
            try:
                rec["sha256"] = _sha256_file(p)
                rec["size_bytes"] = p.stat().st_size
            except OSError as e:
                rec["sha256_error"] = str(e)
        inputs.append(rec)

    return {
        "schema_version": "training_lineage_v1",
        "build_id": build_id,
        "generated_at": _utc_now_iso(),
        "dataset_date": dataset_date,
        "row_counts": row_counts,
        "inputs": inputs,
        "config_snapshot": {
            "dataset_version": cfg.dataset_version,
            "schema_version": cfg.schema_version,
            "train_frac": cfg.train_frac,
            "val_frac": cfg.val_frac,
            "eval_frac": cfg.eval_frac,
            "random_seed": cfg.random_seed,
            "include_ambiguous": cfg.include_ambiguous,
            "ambiguous_fraction": cfg.ambiguous_fraction,
            "local_source_glob": cfg.local_source_glob,
            "s3_source_prefix": cfg.s3_source_prefix,
            "feedback_glob": cfg.feedback_glob,
            "fairness_slice_columns": list(cfg.fairness_slice_columns),
        },
    }


def _resolve_parquet_engine() -> str:
    try:
        import pyarrow  # noqa: F401

        return "pyarrow"
    except ImportError:
        pass
    try:
        import fastparquet  # noqa: F401

        return "fastparquet"
    except ImportError as e:
        raise DatasetBuildError("Install pyarrow or fastparquet.") from e


def _upload_s3_df(
    client, bucket: str, key: str, df: pd.DataFrame, engine: str
) -> None:
    import io

    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine=engine)
    buf.seek(0)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/octet-stream",
    )


def run_dataset_build(
    *,
    config: Optional[DatasetBuildConfig] = None,
) -> DatasetBuildResult:
    cfg = config or DatasetBuildConfig.from_env()
    engine = _resolve_parquet_engine()
    build_id = str(uuid.uuid4())

    if cfg.s3_source_prefix and cfg.s3_bucket:
        data, input_keys = load_s3_labeled_frames(cfg)
    else:
        data, input_keys = load_local_labeled_frames(cfg.local_source_glob)

    feedback_meta: dict[str, Any] = {}
    if cfg.feedback_glob:
        fb_paths = discover_feedback_paths(cfg.feedback_glob)
        if fb_paths:
            fb_df = load_moderation_feedback_jsonl(fb_paths)
            data, feedback_meta = apply_moderation_feedback_overlay(data, fb_df)

    candidates = filter_candidates(data, cfg)

    split_col = assign_thread_splits(candidates, cfg)
    if split_col.isna().any():
        raise DatasetBuildError("Some rows could not be assigned a split")

    built = build_training_frame(candidates, split_col)

    train_part = built[built["split"] == "train"].drop(columns=["split"])
    val_part = built[built["split"] == "val"].drop(columns=["split"])
    eval_part = built[built["split"] == "eval"].drop(columns=["split"])

    train_df = finalize_split(train_part)
    val_df = finalize_split(val_part)
    eval_df = finalize_split(eval_part)

    dataset_date = cfg.dataset_date
    if not dataset_date:
        ts = pd.concat(
            [train_df["event_time"], val_df["event_time"], eval_df["event_time"]],
            ignore_index=True,
        )
        dataset_date = str(ts.min().date()) if len(ts) else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    out_dir = cfg.output_root / "datasets" / dataset_date
    out_dir.mkdir(parents=True, exist_ok=True)

    train_path = out_dir / "train.parquet"
    val_path = out_dir / "val.parquet"
    eval_path = out_dir / "eval.parquet"
    manifest_path = out_dir / "manifest.json"
    quality_path = out_dir / "quality_report.json"
    lineage_path = out_dir / "training_lineage.json"

    row_counts = {"train": len(train_df), "val": len(val_df), "eval": len(eval_df)}

    quality = validate_and_report(train_df, val_df, eval_df, cfg)
    quality["dataset_date"] = dataset_date
    quality["build_id"] = build_id
    quality["input_keys"] = input_keys
    quality["moderation_feedback"] = feedback_meta
    quality["thread_counts"] = {
        "train": int(train_df["thread_id"].nunique()),
        "val": int(val_df["thread_id"].nunique()),
        "eval": int(eval_df["thread_id"].nunique()),
    }

    lineage = build_training_lineage(
        build_id=build_id,
        dataset_date=dataset_date,
        input_keys=input_keys,
        cfg=cfg,
        row_counts=row_counts,
    )

    if cfg.fail_on_quality_error and not quality.get("ok", False):
        quality["export_status"] = "blocked_no_parquet"
        quality_path.write_text(json.dumps(quality, indent=2), encoding="utf-8")
        lineage_path.write_text(json.dumps(lineage, indent=2), encoding="utf-8")
        raise DatasetBuildError(
            "Dataset quality checks failed (see quality_report.json): "
            + "; ".join(quality.get("errors", [])[:8])
        )

    train_df.to_parquet(train_path, index=False, engine=engine)
    val_df.to_parquet(val_path, index=False, engine=engine)
    eval_df.to_parquet(eval_path, index=False, engine=engine)

    manifest: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_date": dataset_date,
        "build_id": build_id,
        "dataset_version": cfg.dataset_version,
        "schema_version": cfg.schema_version,
        "training_row_schema_version": TRAINING_ROW_SCHEMA_VERSION,
        "quality_report_schema_version": QUALITY_REPORT_SCHEMA_VERSION,
        "lineage_path": str(lineage_path.name),
        "training_export_columns": list(TRAINING_EXPORT_COLUMNS),
        "source": "integrated_labeled_messages",
        "source_type": "synthetic_and_or_s3_nightly",
        "input_keys": input_keys,
        "output_paths": {
            "train": str(train_path),
            "val": str(val_path),
            "eval": str(eval_path),
            "quality_report": str(quality_path),
            "training_lineage": str(lineage_path),
        },
        "s3_output_keys": {},
        "candidate_selection_policy": (
            "Reviewed messages only; optional ambiguous subsample; "
            "inference score columns stripped; prior_violation_count split-safe causal; "
            "PII / identifier columns stripped before export (see privacy_policy)"
        ),
        "privacy_policy": {
            "training_parquet_columns": list(TRAINING_EXPORT_COLUMNS),
            "stripped_column_groups": ["inference_scores", "raw_user_identifiers"],
        },
        "ambiguous_handling": {
            "included": cfg.include_ambiguous,
            "fraction": cfg.ambiguous_fraction if cfg.include_ambiguous else 0.0,
        },
        "label_mapping_version": "moderation_label_to_final_label_toxic_v1",
        "split_strategy": "thread_safe_time_split_v1",
        "leakage_prevention": [
            "Threads assigned to exactly one split by thread_start_time ordering",
            "prior_violation_count cumsum within (split, user_hash) only",
            "No inference / model score columns in export",
        ],
        "rows": row_counts,
        "quality_ok": quality.get("ok", False),
        "moderation_feedback_overlay": feedback_meta,
        "generated_at": _utc_now_iso(),
    }

    quality["export_status"] = "written"
    lineage_path.write_text(json.dumps(lineage, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    quality_path.write_text(json.dumps(quality, indent=2), encoding="utf-8")

    if cfg.s3_bucket and not cfg.skip_s3_upload:
        client = _make_s3_client(cfg)
        base = (cfg.s3_output_prefix or f"datasets/{dataset_date}").strip("/")
        s3_keys = {
            "train": f"{base}/train.parquet",
            "val": f"{base}/val.parquet",
            "eval": f"{base}/eval.parquet",
            "manifest": f"{base}/manifest.json",
            "quality": f"{base}/quality_report.json",
            "lineage": f"{base}/training_lineage.json",
        }
        _upload_s3_df(client, cfg.s3_bucket, s3_keys["train"], train_df, engine)
        _upload_s3_df(client, cfg.s3_bucket, s3_keys["val"], val_df, engine)
        _upload_s3_df(client, cfg.s3_bucket, s3_keys["eval"], eval_df, engine)
        client.put_object(
            Bucket=cfg.s3_bucket,
            Key=s3_keys["manifest"],
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        client.put_object(
            Bucket=cfg.s3_bucket,
            Key=s3_keys["quality"],
            Body=json.dumps(quality, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        client.put_object(
            Bucket=cfg.s3_bucket,
            Key=s3_keys["lineage"],
            Body=json.dumps(lineage, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        manifest["s3_output_keys"] = s3_keys
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return DatasetBuildResult(
        train_path=train_path,
        val_path=val_path,
        eval_path=eval_path,
        manifest_path=manifest_path,
        quality_report_path=quality_path,
        lineage_path=lineage_path,
        manifest=manifest,
        quality_report=quality,
        row_counts=row_counts,
    )

