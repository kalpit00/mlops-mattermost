"""
CLI: ``python -m data.pipelines.cli_synthetic`` from repository root.

Environment variables configure volume, dates, rate, and delivery mode; see
``SyntheticGeneratorConfig.from_env`` in ``synthetic_messages.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Mattermost-like messages and moderation labels."
    )
    parser.add_argument(
        "--dry-print",
        action="store_true",
        help="Load config and print effective settings without generating data",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from data.pipelines.synthetic_messages import (
        SyntheticGeneratorConfig,
        run_synthetic_message_generator,
    )

    cfg = SyntheticGeneratorConfig.from_env()
    if args.dry_print:
        print("Synthetic generator config (from env + defaults):")
        for k, v in sorted(cfg.__dict__.items()):
            print(f"  {k}: {v}")
        return 0

    try:
        result = run_synthetic_message_generator(config=cfg)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("Synthetic generation OK")
    print(f"  delivery_mode: {cfg.delivery_mode}")
    print(f"  total_messages: {result.total_messages}")
    print(f"  days: {result.days_written}")
    print(f"  http_posts_succeeded: {result.http_posts_succeeded}")
    if cfg.delivery_mode == "artifact":
        print(
            "  (HTTP posts are skipped in artifact mode; set "
            "MLOPS_SYNTHETIC_DELIVERY_MODE=http or both and MLOPS_MM_BASE_URL, "
            "MLOPS_MM_TOKEN, MLOPS_MM_CHANNEL_ID to post into Mattermost.)"
        )
    if result.http_errors:
        print(f"  http_errors ({len(result.http_errors)}):")
        for err in result.http_errors[:5]:
            print(f"    - {err}")
    print(f"  message parquet (first): {result.message_paths[:1]}")
    print(f"  label parquet (first): {result.label_paths[:1]}")
    print(f"  s3 keys (count): {len(result.s3_keys_uploaded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
