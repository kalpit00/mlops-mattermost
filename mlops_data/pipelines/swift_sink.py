"""
Optional OpenStack Swift sink for school-project deployments.

This repo primarily writes artifacts to an S3-compatible store (MinIO). If you also want a
copy in Chameleon (Swift), set:

- MLOPS_SWIFT_ENABLED=1
- MLOPS_SWIFT_CLOUDS_YAML_PATH=clouds.yaml   (default: clouds.yaml in cwd)
- MLOPS_SWIFT_CLOUD=openstack               (default: openstack)
- MLOPS_SWIFT_CONTAINER=Objstore_proj17     (required when enabled)
- MLOPS_SWIFT_PREFIX=moderation-data       (default: moderation-data)

Artifacts are uploaded under: <prefix>/<object_name>
"""

from __future__ import annotations

import os
from pathlib import Path


def _b(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def swift_enabled() -> bool:
    return _b("MLOPS_SWIFT_ENABLED", False)


def swift_upload_file(*, local_path: Path, object_name: str) -> None:
    """
    Best-effort upload of one local file to Swift.

    object_name should be the "MinIO-style" key, e.g. raw/jigsaw/train.csv
    """
    if not swift_enabled():
        return

    container = os.environ.get("MLOPS_SWIFT_CONTAINER", "").strip()
    if not container:
        raise RuntimeError("MLOPS_SWIFT_CONTAINER is required when MLOPS_SWIFT_ENABLED=1")

    clouds_path = os.environ.get("MLOPS_SWIFT_CLOUDS_YAML_PATH", "clouds.yaml").strip()
    cloud = os.environ.get("MLOPS_SWIFT_CLOUD", "openstack").strip() or "openstack"
    prefix = os.environ.get("MLOPS_SWIFT_PREFIX", "moderation-data").strip().strip("/")

    if not local_path.is_file():
        raise FileNotFoundError(str(local_path))

    # openstacksdk reads clouds.yaml via OS_CLIENT_CONFIG_FILE / standard locations.
    # Keep it simple: point OS_CLIENT_CONFIG_FILE at the provided path unless the user
    # already set it.
    os.environ.setdefault("OS_CLIENT_CONFIG_FILE", clouds_path)

    import openstack  # type: ignore

    conn = openstack.connect(cloud=cloud)
    name = f"{prefix}/{object_name.lstrip('/')}" if prefix else object_name.lstrip("/")

    try:
        # Ensure container exists (idempotent in Swift).
        try:
            conn.object_store.create_container(container)
        except Exception:
            pass

        conn.create_object(container=container, name=name, filename=str(local_path))
    finally:
        try:
            conn.close()
        except Exception:
            pass

