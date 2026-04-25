"""
Lightweight quality + drift monitoring for the integrated MLOps paths.

**Stages**
1. **Ingestion** — external parquet (e.g. Jigsaw ``comments_binary.parquet``): row counts,
   text null rate, label balance, text-length stats.
2. **Training** — ``train.parquet`` from ``dataset_build``: text length, channel mix,
   label distribution; can persist **reference** stats for drift.
3. **Live** — ``online_features_v1.jsonl`` + ``online_scores_v1.jsonl`` (+ optional
   ``moderation_feedback_v1.jsonl``): same aggregates vs reference.

**Drift** — compare live vs reference on message-length mean, channel mix (max category
   delta), score mean/std (if scores exist), label distribution (if feedback/labels exist).
Threshold breaches set ``breaches[].breached: true``.

**Schedule** — ``python -m data.pipelines.cli_monitoring`` (cron / CI).

**Env** — see ``MonitoringConfig.from_env``; outputs under ``MLOPS_MONITOR_OUTPUT_DIR``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPORT_SCHEMA_VERSION = "mlops_monitor_report_v1"
REFERENCE_SCHEMA_VERSION = "mlops_monitor_reference_v1"


class MonitoringError(Exception):
    pass


@dataclass
class MonitoringConfig:
    """Thresholds are simple absolute / relative rules; tune via env for your milestone."""

    output_dir: Path = field(default_factory=lambda: Path("data/mlmoderation/monitoring"))
    ingestion_parquet: Path | None = None
    train_parquet: Path | None = None
    reference_json: Path | None = None
    write_reference_from_train: bool = False
    live_features_jsonl: Path | None = None
    live_scores_jsonl: Path | None = None
    live_feedback_jsonl: Path | None = None
    live_max_lines: int = 200_000
    drift_mean_len_abs: float = 40.0
    drift_channel_l1_max: float = 0.15
    drift_score_mean_abs: float = 0.12
    drift_label_l1_max: float = 0.20
    write_parquet_summary: bool = True

    @classmethod
    def from_env(cls, **overrides: Any) -> MonitoringConfig:
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

        def _b(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        def _p(name: str) -> Path | None:
            v = os.environ.get(name, "").strip()
            return Path(v).expanduser() if v else None

        _mod = os.environ.get("MLOPS_MONITOR_OUTPUT_DIR")
        if _mod is None or not str(_mod).strip():
            _mod = "data/mlmoderation/monitoring"
        root = Path(_mod).expanduser()

        cfg = cls(
            output_dir=root,
            ingestion_parquet=_p("MLOPS_MONITOR_INGESTION_PARQUET"),
            train_parquet=_p("MLOPS_MONITOR_TRAIN_PARQUET"),
            reference_json=_p("MLOPS_MONITOR_REFERENCE_JSON"),
            write_reference_from_train=_b("MLOPS_MONITOR_WRITE_REFERENCE_FROM_TRAIN", False),
            live_features_jsonl=_p("MLOPS_MONITOR_LIVE_FEATURES_JSONL")
            or Path("data/mlmoderation/logs/online_features_v1.jsonl"),
            live_scores_jsonl=_p("MLOPS_MONITOR_LIVE_SCORES_JSONL")
            or Path("data/mlmoderation/logs/online_scores_v1.jsonl"),
            live_feedback_jsonl=_p("MLOPS_MONITOR_LIVE_FEEDBACK_JSONL"),
            live_max_lines=_i("MLOPS_MONITOR_LIVE_MAX_LINES", 200_000),
            drift_mean_len_abs=_f("MLOPS_MONITOR_DRIFT_MEAN_LEN_ABS", 40.0),
            drift_channel_l1_max=_f("MLOPS_MONITOR_DRIFT_CHANNEL_L1", 0.15),
            drift_score_mean_abs=_f("MLOPS_MONITOR_DRIFT_SCORE_MEAN_ABS", 0.12),
            drift_label_l1_max=_f("MLOPS_MONITOR_DRIFT_LABEL_L1", 0.20),
            write_parquet_summary=_b("MLOPS_MONITOR_WRITE_PARQUET", True),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, v)
        return cfg


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_length_stats(text_series: pd.Series) -> dict[str, Any]:
    s = text_series.fillna("").astype(str)
    lengths = s.str.len()
    if len(lengths) == 0:
        return {"n": 0, "mean": None, "std": None, "p50": None, "p90": None}
    return {
        "n": int(len(lengths)),
        "mean": float(lengths.mean()),
        "std": float(lengths.std()) if len(lengths) > 1 else 0.0,
        "p50": float(lengths.quantile(0.5)),
        "p90": float(lengths.quantile(0.9)),
    }


def normalized_mix(series: pd.Series, top_n: int = 20) -> dict[str, float]:
    if series is None or len(series) == 0:
        return {}
    vc = series.astype(str).value_counts(normalize=True)
    out = {str(k): float(v) for k, v in vc.head(top_n).items()}
    other = 1.0 - sum(out.values())
    if other > 1e-6:
        out["_other"] = max(0.0, float(other))
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def normalize_binary_label_dist(dist: dict[str, float]) -> dict[str, float]:
    """Map training 0/1 and feedback non_toxic/toxic into '0'/'1' buckets."""
    out: dict[str, float] = {}
    for k, v in dist.items():
        kk = str(k).strip().lower()
        if kk in ("non_toxic", "nontoxic", "0", "false", "safe", "clean"):
            out["0"] = out.get("0", 0.0) + float(v)
        elif kk in ("toxic", "1", "true", "ambiguous"):
            if kk == "ambiguous":
                out["ambiguous"] = out.get("ambiguous", 0.0) + float(v)
            else:
                out["1"] = out.get("1", 0.0) + float(v)
        else:
            out[f"_{kk}"] = float(v)
    return out


def max_category_drift(ref: dict[str, float], live: dict[str, float]) -> float:
    keys = set(ref) | set(live)
    if not keys:
        return 0.0
    return max(abs(ref.get(k, 0.0) - live.get(k, 0.0)) for k in keys)


def score_distribution(scores: pd.Series) -> dict[str, Any]:
    s = pd.to_numeric(scores, errors="coerce").dropna()
    if len(s) == 0:
        return {"n": 0, "mean": None, "std": None, "p50": None, "p90": None}
    return {
        "n": int(len(s)),
        "mean": float(s.mean()),
        "std": float(s.std()) if len(s) > 1 else 0.0,
        "p50": float(s.quantile(0.5)),
        "p90": float(s.quantile(0.9)),
    }


def build_reference_payload(
    *,
    source: str,
    message_length: dict[str, Any],
    channel_mix: dict[str, float],
    label_distribution: dict[str, float] | None,
    score_distribution: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "source": source,
        "message_length": message_length,
        "channel_type_mix": channel_mix,
        "label_distribution": label_distribution or {},
        "score_distribution": score_distribution or {},
    }


def load_reference(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MonitoringError(f"Reference file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def report_ingestion(parquet_path: Path) -> dict[str, Any]:
    if not parquet_path.is_file():
        return {"ok": False, "error": f"missing_file:{parquet_path}"}
    df = pd.read_parquet(parquet_path)
    text_col = "text" if "text" in df.columns else None
    label_col = None
    for c in ("label_toxic", "final_label_toxic"):
        if c in df.columns:
            label_col = c
            break
    out: dict[str, Any] = {
        "ok": True,
        "path": str(parquet_path),
        "rows": len(df),
        "columns": list(df.columns),
    }
    if text_col:
        null_rate = float(df[text_col].isna().mean()) + float(
            (df[text_col].astype(str).str.len() == 0).mean()
        )
        out["text_null_or_empty_rate"] = round(null_rate, 6)
        out["message_length"] = text_length_stats(df[text_col])
    if label_col:
        vc = df[label_col].value_counts(normalize=True)
        out["label_distribution"] = {str(k): round(float(v), 6) for k, v in vc.items()}
    return out


def report_training(train_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (human report section, reference_payload for drift)."""
    if not train_path.is_file():
        return (
            {"ok": False, "error": f"missing_file:{train_path}"},
            build_reference_payload(
                source="train_missing",
                message_length={"n": 0},
                channel_mix={},
                label_distribution=None,
                score_distribution=None,
            ),
        )
    df = pd.read_parquet(train_path)
    text_col = "text" if "text" in df.columns else None
    ch_col = "channel_type" if "channel_type" in df.columns else None
    lab_col = "final_label_toxic" if "final_label_toxic" in df.columns else None

    msg_len = text_length_stats(df[text_col]) if text_col else {"n": 0}
    ch_mix = normalized_mix(df[ch_col]) if ch_col else {}
    lab_dist = None
    if lab_col:
        vc = df[lab_col].value_counts(normalize=True)
        lab_dist = {str(k): float(v) for k, v in vc.items()}

    ref = build_reference_payload(
        source=str(train_path),
        message_length=msg_len,
        channel_mix=ch_mix,
        label_distribution=lab_dist,
        score_distribution=None,
    )

    report = {
        "ok": True,
        "path": str(train_path),
        "rows": len(df),
        "message_length": msg_len,
        "channel_type_mix": ch_mix,
        "label_distribution": lab_dist,
    }
    return report, ref


def read_jsonl_tail(path: Path, max_lines: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def report_live(
    features_path: Path,
    scores_path: Path,
    feedback_path: Path | None,
    max_lines: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns (report section, stats dict comparable to reference:
    message_length, channel_type_mix, label_distribution, score_distribution).
    """
    feats = read_jsonl_tail(features_path, max_lines)
    scores = read_jsonl_tail(scores_path, max_lines)
    if not feats:
        empty_ref = build_reference_payload(
            source="live_empty",
            message_length={"n": 0},
            channel_mix={},
            label_distribution=None,
            score_distribution=None,
        )
        return (
            {
                "ok": True,
                "note": "no_feature_rows",
                "features_path": str(features_path),
                "feature_rows": 0,
            },
            empty_ref,
        )

    df_f = pd.DataFrame(feats)
    text_col = "text" if "text" in df_f.columns else None
    ch_col = "channel_type" if "channel_type" in df_f.columns else None
    msg_len = text_length_stats(df_f[text_col]) if text_col else {"n": len(df_f)}
    ch_mix = normalized_mix(df_f[ch_col]) if ch_col else {}

    df_s = pd.DataFrame(scores) if scores else pd.DataFrame()
    score_dist: dict[str, Any] = {"n": 0}
    if len(df_s) and "toxicity_score" in df_s.columns:
        if "post_id" in df_f.columns and "post_id" in df_s.columns:
            merged = df_f.merge(
                df_s[["post_id", "toxicity_score"]],
                on="post_id",
                how="inner",
            )
            score_dist = score_distribution(merged["toxicity_score"])
        else:
            score_dist = score_distribution(df_s["toxicity_score"])

    lab_dist: dict[str, float] | None = None
    if feedback_path and feedback_path.is_file():
        fb = read_jsonl_tail(feedback_path, max_lines)
        if fb:
            df_b = pd.DataFrame(fb)
            if "moderation_label" in df_b.columns:
                vc = df_b["moderation_label"].astype(str).value_counts(normalize=True)
                lab_dist = {str(k): float(v) for k, v in vc.items()}

    live_ref = build_reference_payload(
        source="live_window",
        message_length=msg_len,
        channel_mix=ch_mix,
        label_distribution=lab_dist,
        score_distribution=score_dist if score_dist.get("n", 0) else None,
    )

    report = {
        "ok": True,
        "features_path": str(features_path),
        "scores_path": str(scores_path),
        "feature_rows": len(df_f),
        "score_rows": len(df_s),
        "message_length": msg_len,
        "channel_type_mix": ch_mix,
        "score_distribution": score_dist,
        "label_distribution": lab_dist,
        "feedback_path": str(feedback_path) if feedback_path else None,
    }
    return report, live_ref


def evaluate_drift(
    reference: dict[str, Any],
    live: dict[str, Any],
    cfg: MonitoringConfig,
) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []

    def check(
        name: str,
        breached: bool,
        detail: dict[str, Any],
    ) -> None:
        breaches.append({"metric": name, "breached": breached, **detail})

    r_len = reference.get("message_length") or {}
    l_len = live.get("message_length") or {}
    rm, lm = r_len.get("mean"), l_len.get("mean")
    if rm is not None and lm is not None and l_len.get("n", 0) > 0:
        delta = abs(float(lm) - float(rm))
        check(
            "message_length_mean",
            delta > cfg.drift_mean_len_abs,
            {"reference_mean": rm, "live_mean": lm, "delta": delta, "threshold": cfg.drift_mean_len_abs},
        )

    r_ch = reference.get("channel_type_mix") or {}
    l_ch = live.get("channel_type_mix") or {}
    if r_ch and l_ch:
        d = max_category_drift(r_ch, l_ch)
        check(
            "channel_type_mix_max_delta",
            d > cfg.drift_channel_l1_max,
            {"max_category_delta": d, "threshold": cfg.drift_channel_l1_max},
        )

    r_sc = reference.get("score_distribution") or {}
    l_sc = live.get("score_distribution") or {}
    if r_sc.get("n") and l_sc.get("n"):
        rsm, lsm = r_sc.get("mean"), l_sc.get("mean")
        if rsm is not None and lsm is not None:
            sd = abs(float(lsm) - float(rsm))
            check(
                "toxicity_score_mean",
                sd > cfg.drift_score_mean_abs,
                {"reference_mean": rsm, "live_mean": lsm, "delta": sd, "threshold": cfg.drift_score_mean_abs},
            )

    r_lb = reference.get("label_distribution") or {}
    l_lb = live.get("label_distribution") or {}
    if r_lb and l_lb:
        d = max_category_drift(
            normalize_binary_label_dist({str(k): float(v) for k, v in r_lb.items()}),
            normalize_binary_label_dist({str(k): float(v) for k, v in l_lb.items()}),
        )
        check(
            "label_distribution_max_delta",
            d > cfg.drift_label_l1_max,
            {"max_label_delta": d, "threshold": cfg.drift_label_l1_max},
        )

    return breaches


def run_monitoring(*, config: Optional[MonitoringConfig] = None) -> dict[str, Any]:
    cfg = config or MonitoringConfig.from_env()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "ingestion": None,
        "training": None,
        "live": None,
        "reference": None,
        "drift": None,
        "any_breach": False,
    }

    if cfg.ingestion_parquet:
        report["ingestion"] = report_ingestion(cfg.ingestion_parquet)

    reference: dict[str, Any] | None = None
    if cfg.reference_json and cfg.reference_json.is_file():
        reference = load_reference(cfg.reference_json)
        report["reference"] = {"source": "file", "path": str(cfg.reference_json)}
    elif cfg.train_parquet:
        train_rep, ref_payload = report_training(cfg.train_parquet)
        report["training"] = train_rep
        reference = ref_payload
        report["reference"] = {"source": "train_parquet", "path": str(cfg.train_parquet)}
        if cfg.write_reference_from_train and train_rep.get("ok"):
            ref_path = cfg.output_dir / "reference_from_train.json"
            ref_path.write_text(json.dumps(ref_payload, indent=2), encoding="utf-8")
            report["reference"]["written"] = str(ref_path)

    live_rep, live_stats = report_live(
        cfg.live_features_jsonl or Path("."),
        cfg.live_scores_jsonl or Path("."),
        cfg.live_feedback_jsonl,
        cfg.live_max_lines,
    )
    report["live"] = live_rep

    drift_breaches: list[dict[str, Any]] = []
    if reference and live_stats.get("message_length", {}).get("n", 0) > 0:
        drift_breaches = evaluate_drift(reference, live_stats, cfg)
        report["any_breach"] = any(b.get("breached") for b in drift_breaches)
    elif reference:
        report["drift_note"] = "live_empty_skipped"
    else:
        report["drift_note"] = "no_reference_skipped"

    report["drift"] = {
        "breaches": drift_breaches,
        "thresholds": {
            "mean_message_length_abs": cfg.drift_mean_len_abs,
            "channel_mix_max_delta": cfg.drift_channel_l1_max,
            "score_mean_abs": cfg.drift_score_mean_abs,
            "label_mix_max_delta": cfg.drift_label_l1_max,
        },
    }

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = cfg.output_dir / f"monitor_report_{day}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["output_json"] = str(json_path)

    if cfg.write_parquet_summary:
        summary_row = {
            "generated_at": report["generated_at"],
            "any_breach": report["any_breach"],
            "ingestion_ok": (report["ingestion"] or {}).get("ok"),
            "training_rows": (report["training"] or {}).get("rows"),
            "live_feature_rows": (report["live"] or {}).get("feature_rows"),
            "live_mean_len": (report["live"] or {}).get("message_length", {}).get("mean"),
            "ref_mean_len": (reference or {}).get("message_length", {}).get("mean") if reference else None,
        }
        pq_path = cfg.output_dir / f"monitor_summary_{day}.parquet"
        try:
            pd.DataFrame([summary_row]).to_parquet(pq_path, index=False)
            report["output_parquet"] = str(pq_path)
        except Exception as e:
            report["output_parquet_error"] = str(e)

    report["promotion_integration"] = {
        "note": (
            "Point cli_promotion_gate at this file via MLOPS_PROMOTION_MONITOR_JSON "
            "or MLOPS_PROMOTION_MONITOR_DIR to block deploy when any_breach is true."
        ),
        "any_breach": report.get("any_breach"),
    }

    return report

