"""
Lightweight promotion / rollback gate from data artifacts.

Reads ``quality_report.json`` (from :mod:`mlops_data.pipelines.dataset_build`) and optionally
the latest monitoring JSON (``monitor_report_*.json``). Exits non-zero from the CLI when
``allow_promotion`` is false.

**Blocks when**
- ``quality_report.ok`` is false (includes severe validation + eval imbalance when configured).
- Monitoring report has ``any_breach`` (drift vs reference).
- Eval label minority fraction is below ``MLOPS_PROMOTION_EVAL_MINORITY_MIN_FRAC`` (redundant
  if quality already encodes this; kept as an explicit second line of defense).

**Env**
See :class:`PromotionGateConfig.from_env`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class PromotionGateError(Exception):
    pass


@dataclass
class PromotionGateConfig:
    quality_report_path: Path | None = None
    manifest_path: Path | None = None
    monitor_report_path: Path | None = None
    eval_minority_min_frac: float = 0.05
    require_monitor_report: bool = False

    @classmethod
    def from_env(cls, **overrides: Any) -> PromotionGateConfig:
        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return float(v)

        def _b(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        def _p(name: str) -> Path | None:
            v = os.environ.get(name, "").strip()
            return Path(v).expanduser() if v else None

        cfg = cls(
            quality_report_path=_p("MLOPS_PROMOTION_QUALITY_REPORT"),
            manifest_path=_p("MLOPS_PROMOTION_MANIFEST"),
            monitor_report_path=_p("MLOPS_PROMOTION_MONITOR_JSON"),
            eval_minority_min_frac=_f("MLOPS_PROMOTION_EVAL_MINORITY_MIN_FRAC", 0.05),
            require_monitor_report=_b("MLOPS_PROMOTION_REQUIRE_MONITOR", False),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, v)
        return cfg


def _label_minority_fraction(counts: dict[str, Any]) -> float | None:
    if not counts:
        return None
    total = sum(int(v) for v in counts.values())
    if total <= 0:
        return None
    return min(int(v) / total for v in counts.values())


def _pick_latest_monitor(dir_path: Path) -> Path | None:
    if not dir_path.is_dir():
        return None
    cands = sorted(dir_path.glob("monitor_report_*.json"))
    return cands[-1] if cands else None


def evaluate_promotion_gate(
    *,
    config: Optional[PromotionGateConfig] = None,
) -> dict[str, Any]:
    cfg = config or PromotionGateConfig.from_env()
    reasons: list[str] = []
    details: dict[str, Any] = {}

    if cfg.quality_report_path is None or not cfg.quality_report_path.is_file():
        raise PromotionGateError(
            "Set MLOPS_PROMOTION_QUALITY_REPORT to quality_report.json (required)."
        )

    q = json.loads(cfg.quality_report_path.read_text(encoding="utf-8"))
    details["quality_schema"] = q.get("schema_version")
    details["quality_ok"] = q.get("ok")

    if not q.get("ok", False):
        details["quality_errors"] = q.get("errors", [])[:20]
        codes = q.get("blocking_codes") or []
        if "eval_label_imbalance" in codes:
            reasons.append("evaluation_data_too_imbalanced")
        else:
            reasons.append("training_data_quality_failed")

    eval_bal = (q.get("label_balance") or {}).get("eval") or {}
    em = _label_minority_fraction(eval_bal)
    details["eval_label_minority_fraction"] = em
    if em is not None and em < cfg.eval_minority_min_frac:
        if "evaluation_data_too_imbalanced" not in reasons:
            reasons.append("evaluation_data_too_imbalanced")
        details["eval_minority_threshold"] = cfg.eval_minority_min_frac

    mon_path = cfg.monitor_report_path
    if mon_path is None:
        mon_dir = Path(os.environ.get("MLOPS_PROMOTION_MONITOR_DIR", "")).expanduser()
        if mon_dir.is_dir():
            mon_path = _pick_latest_monitor(mon_dir)
    if mon_path and mon_path.is_file():
        m = json.loads(mon_path.read_text(encoding="utf-8"))
        details["monitor_path"] = str(mon_path)
        details["monitor_any_breach"] = m.get("any_breach")
        if m.get("any_breach"):
            reasons.append("live_drift_too_high")
            details["drift_breaches"] = [
                b for b in (m.get("drift") or {}).get("breaches", []) if b.get("breached")
            ]
    elif cfg.require_monitor_report:
        reasons.append("monitor_report_missing")

    allow = len(reasons) == 0
    out: dict[str, Any] = {
        "schema_version": "promotion_gate_v1",
        "allow_promotion": allow,
        "block_reasons": reasons,
        "details": details,
    }
    if cfg.manifest_path and cfg.manifest_path.is_file():
        man = json.loads(cfg.manifest_path.read_text(encoding="utf-8"))
        out["manifest_build_id"] = man.get("build_id")
        out["manifest_dataset_date"] = man.get("dataset_date")
    return out


def run_promotion_gate(
    *,
    config: Optional[PromotionGateConfig] = None,
) -> dict[str, Any]:
    return evaluate_promotion_gate(config=config)
