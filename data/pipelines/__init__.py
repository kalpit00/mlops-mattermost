"""
MLOps data pipelines for the Mattermost moderation / toxicity track.

Tracked source lives here; large artifacts use paths under ``data/`` (gitignored)
or object storage keys documented in each pipeline module.

Imports are lazy so ``python -m data.pipelines.cli_jigsaw --help`` works without
optional runtime deps (e.g. ``boto3``) until you actually run an ingest.
"""

from typing import TYPE_CHECKING, Any

__all__ = [
    "JigsawIngestionConfig",
    "JigsawIngestionResult",
    "JigsawIngestionError",
    "run_jigsaw_ingestion",
    "SyntheticGeneratorConfig",
    "SyntheticGeneratorResult",
    "SyntheticGeneratorError",
    "run_synthetic_message_generator",
    "DatasetBuildConfig",
    "DatasetBuildResult",
    "DatasetBuildError",
    "run_dataset_build",
    "MonitoringConfig",
    "MonitoringError",
    "run_monitoring",
    "PromotionGateConfig",
    "PromotionGateError",
    "run_promotion_gate",
]

_JIGSAW_EXPORTS = frozenset(
    {
        "JigsawIngestionConfig",
        "JigsawIngestionResult",
        "JigsawIngestionError",
        "run_jigsaw_ingestion",
    }
)
_SYNTHETIC_EXPORTS = frozenset(
    {
        "SyntheticGeneratorConfig",
        "SyntheticGeneratorResult",
        "SyntheticGeneratorError",
        "run_synthetic_message_generator",
    }
)
_DATASET_EXPORTS = frozenset(
    {
        "DatasetBuildConfig",
        "DatasetBuildResult",
        "DatasetBuildError",
        "run_dataset_build",
    }
)
_MONITORING_EXPORTS = frozenset(
    {
        "MonitoringConfig",
        "MonitoringError",
        "run_monitoring",
    }
)
_PROMOTION_EXPORTS = frozenset(
    {
        "PromotionGateConfig",
        "PromotionGateError",
        "run_promotion_gate",
    }
)

if TYPE_CHECKING:
    from .jigsaw_ingestion import (
        JigsawIngestionConfig,
        JigsawIngestionError,
        JigsawIngestionResult,
        run_jigsaw_ingestion,
    )
    from .synthetic_messages import (
        SyntheticGeneratorConfig,
        SyntheticGeneratorError,
        SyntheticGeneratorResult,
        run_synthetic_message_generator,
    )
    from .dataset_build import (
        DatasetBuildConfig,
        DatasetBuildError,
        DatasetBuildResult,
        run_dataset_build,
    )
    from .monitoring import MonitoringConfig, MonitoringError, run_monitoring
    from .promotion_gate import PromotionGateConfig, PromotionGateError, run_promotion_gate


def __getattr__(name: str) -> Any:
    if name in _JIGSAW_EXPORTS:
        from . import jigsaw_ingestion as _m

        return getattr(_m, name)
    if name in _SYNTHETIC_EXPORTS:
        from . import synthetic_messages as _m

        return getattr(_m, name)
    if name in _DATASET_EXPORTS:
        from . import dataset_build as _m

        return getattr(_m, name)
    if name in _MONITORING_EXPORTS:
        from . import monitoring as _m

        return getattr(_m, name)
    if name in _PROMOTION_EXPORTS:
        from . import promotion_gate as _m

        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
