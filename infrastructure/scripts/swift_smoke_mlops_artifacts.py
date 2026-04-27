"""
Smoke test: run a small MLOps pipeline step and confirm artifacts appear in Swift.

This uses the repo's existing pipelines, and the Swift sink we added in `mlops_data/pipelines/swift_sink.py`.

Env vars (Swift):
- MLOPS_SWIFT_ENABLED=1
- MLOPS_SWIFT_CLOUDS_YAML_PATH=clouds.yaml   (default: clouds.yaml)
- MLOPS_SWIFT_CLOUD=openstack               (default: openstack)
- MLOPS_SWIFT_CONTAINER=Objstore_proj17     (required)
- MLOPS_SWIFT_PREFIX=moderation-data       (default: moderation-data)

Pipeline:
- Runs `python -m mlops_data.pipelines.cli_synthetic` with small volumes.
- Confirms at least one object exists in Swift under:
    <prefix>/nightly/<date>/labeled_messages.parquet
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def swift_connect():
    os.environ.setdefault("OS_CLIENT_CONFIG_FILE", env("MLOPS_SWIFT_CLOUDS_YAML_PATH", "clouds.yaml"))
    os.environ.setdefault("OS_CLOUD", env("MLOPS_SWIFT_CLOUD", "openstack") or "openstack")
    import openstack  # type: ignore

    return openstack.connect(cloud=os.environ["OS_CLOUD"])


def main() -> int:
    if env("MLOPS_SWIFT_ENABLED", "0").lower() not in ("1", "true", "yes", "on"):
        print("Set MLOPS_SWIFT_ENABLED=1 to run this test.", file=sys.stderr)
        return 2

    container = env("MLOPS_SWIFT_CONTAINER")
    if not container:
        print("Missing MLOPS_SWIFT_CONTAINER", file=sys.stderr)
        return 2

    prefix = env("MLOPS_SWIFT_PREFIX", "moderation-data").strip().strip("/")
    today = date.today().isoformat()
    expected = f"{prefix}/nightly/{today}/labeled_messages.parquet" if prefix else f"nightly/{today}/labeled_messages.parquet"

    # Keep it small and quick.
    run_env = os.environ.copy()
    run_env.setdefault("MLOPS_SYNTHETIC_TEST_MODE", "1")
    run_env.setdefault("MLOPS_SYNTHETIC_N_DAYS", "1")
    run_env.setdefault("MLOPS_SYNTHETIC_MESSAGES_PER_DAY", "15")
    run_env.setdefault("MLOPS_SYNTHETIC_N_USERS", "10")
    run_env.setdefault("MLOPS_SYNTHETIC_N_BASE_THREADS", "4")
    run_env.setdefault("MLOPS_SYNTHETIC_DELIVERY_MODE", "artifact")
    run_env.setdefault("MLOPS_SYNTHETIC_WRITE_JSONL", "0")
    run_env.setdefault("MLOPS_SYNTHETIC_WRITE_COMBINED", "1")

    print("Running synthetic generator...")
    p = subprocess.run(
        [sys.executable, "-m", "mlops_data.pipelines.cli_synthetic"],
        env=run_env,
        cwd=os.getcwd(),
        check=False,
        text=True,
    )
    if p.returncode != 0:
        print("Synthetic generator failed.", file=sys.stderr)
        return p.returncode

    print("Checking Swift for:", expected)
    conn = swift_connect()
    try:
        for obj in conn.object_store.objects(container, prefix=expected):
            name = getattr(obj, "name", "") or ""
            if name == expected:
                print("OK: found", name)
                return 0
        # Some SDKs don't yield exact key on prefix match; fallback to a short scan.
        scan_prefix = f"{prefix}/nightly/{today}/" if prefix else f"nightly/{today}/"
        for obj in conn.object_store.objects(container, prefix=scan_prefix):
            name = getattr(obj, "name", "") or ""
            if name.endswith("/labeled_messages.parquet"):
                print("OK: found", name)
                return 0
        print("NOT FOUND in Swift under prefix:", scan_prefix, file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

