"""
Promotion gate CLI: ``python -m data.pipelines.cli_promotion_gate``

Use in CI before deploy / model promotion. Set ``MLOPS_PROMOTION_QUALITY_REPORT`` and
optionally monitoring paths (see ``promotion_gate`` module).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Block promotion when quality, eval balance, or drift checks fail."
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print full gate result JSON to stdout",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from data.pipelines.promotion_gate import PromotionGateConfig, PromotionGateError, run_promotion_gate

    try:
        report = run_promotion_gate(config=PromotionGateConfig.from_env())
    except PromotionGateError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.print_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(
            "promotion_gate:",
            "ALLOW" if report.get("allow_promotion") else "BLOCK",
        )
        for r in report.get("block_reasons") or []:
            print(f"  - {r}")

    return 0 if report.get("allow_promotion") else 1


if __name__ == "__main__":
    raise SystemExit(main())
