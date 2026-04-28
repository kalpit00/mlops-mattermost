#!/usr/bin/env python3
"""
Point MLflow registered-model aliases at the best sweep-produced version so serving
initContainers can resolve get_model_version_by_alias(...).

Prefers versions whose training run has param quality_gate_passed=true (see training/train.py).
If none qualify, uses the latest registered version (warning printed).

Typical use inside the mlflow pod (SQLite backend + artifacts on MinIO):

  kubectl -n platform exec -i deploy/mlflow -- \\
    env MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python3 - < infrastructure/scripts/promote_mlflow_aliases.py

Or from any environment with MLFLOW_TRACKING_URI set (e.g. port-forward to MLflow).
"""

from __future__ import annotations

import argparse
import os
import sys


def _pick_version(client, model_name: str, fallback_latest: bool):
    versions = client.search_model_versions(f"name='{model_name}'")
    if not versions:
        print(f"No registered versions found for model {model_name!r}. Run the training sweep first.", file=sys.stderr)
        sys.exit(1)

    # Highest numeric version first
    versions_sorted = sorted(versions, key=lambda v: int(v.version), reverse=True)

    chosen = None
    chosen_reason = ""
    for mv in versions_sorted:
        try:
            run = client.get_run(mv.run_id)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: could not load run {mv.run_id} for v{mv.version}: {exc}", file=sys.stderr)
            continue
        gate = (run.data.params or {}).get("quality_gate_passed", "").lower()
        if gate == "true":
            chosen = mv
            chosen_reason = "latest version with quality_gate_passed=true"
            break

    if chosen is None:
        if not fallback_latest:
            print(
                "No version had quality_gate_passed=true; refusing to promote (--no-fallback-latest).",
                file=sys.stderr,
            )
            sys.exit(1)
        chosen = versions_sorted[0]
        chosen_reason = "fallback: highest version (no gate-passed version found)"

    assert chosen is not None
    return chosen, chosen_reason


def main() -> None:
    parser = argparse.ArgumentParser(description="Set MLflow model aliases after sweep runs.")
    parser.add_argument(
        "--tracking-uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"),
        help="MLflow tracking URI (default: env MLFLOW_TRACKING_URI or http://127.0.0.1:5000)",
    )
    parser.add_argument("--model", default="tfidf_logreg", help="Registered model name")
    parser.add_argument(
        "--aliases",
        nargs="+",
        default=["staging", "canary", "production"],
        help="Aliases to update (default: staging canary production)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print chosen version and aliases without updating MLflow",
    )
    parser.add_argument(
        "--no-fallback-latest",
        dest="fallback_latest",
        action="store_false",
        help="Fail if no quality_gate_passed=true version exists",
    )
    parser.set_defaults(fallback_latest=True)

    args = parser.parse_args()

    from mlflow import MlflowClient

    client = MlflowClient(args.tracking_uri)

    chosen, reason = _pick_version(client, args.model, args.fallback_latest)

    print(f"Chosen {args.model} version {chosen.version} ({reason}).")
    print(f"  run_id={chosen.run_id} status={chosen.status}")

    if args.dry_run:
        print("Dry run: not updating aliases.")
        return

    vnum = int(chosen.version)
    for alias in args.aliases:
        client.set_registered_model_alias(args.model, alias, vnum)
        print(f"  set alias {alias!r} -> version {vnum}")

    print("Aliases updated.")


if __name__ == "__main__":
    main()
