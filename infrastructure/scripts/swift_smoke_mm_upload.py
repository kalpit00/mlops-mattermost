"""
Smoke test: upload a small attachment via Mattermost API, then confirm it was replicated to Swift.

Requirements:
- Mattermost reachable (MM_BASE_URL)
- Auth via either:
  - Personal access token (MM_TOKEN) OR
  - Username/password login (MM_USERNAME, MM_PASSWORD)
- A channel id you can upload into (MM_CHANNEL_ID)
- Swift creds available via clouds.yaml (OpenStack application credential)

Env vars:
- MM_BASE_URL              e.g. http://129-114-27-105.nip.io
- MM_TOKEN                 personal access token (optional if MM_USERNAME/MM_PASSWORD provided)
- MM_USERNAME              username/email for login (optional if MM_TOKEN provided)
- MM_PASSWORD              password for login (optional if MM_TOKEN provided)
- MM_CHANNEL_ID            target channel id
- MM_FILENAME              optional, default: swift_smoke.txt
- MM_CONTENT               optional, default: "hello swift"

- OS_CLIENT_CONFIG_FILE or SWIFT_CLOUDS_YAML_PATH (default: clouds.yaml)
- SWIFT_CLOUD              default: openstack
- SWIFT_CONTAINER          required, e.g. Objstore_proj17
- SWIFT_PREFIX             default: mattermost

Notes:
This does not assume the MinIO bucket name used by Mattermost. It searches Swift for an
object whose name ends with: "/<upload_id>/<filename>" under the prefix.
"""

from __future__ import annotations

import os
import sys
import time
import json
import urllib.request
import urllib.error
import http.cookiejar
from typing import Any


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _build_opener(token: str) -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(jar)]
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = []
    if token:
        opener.addheaders.append(("Authorization", f"Bearer {token}"))
    return opener


def login_and_get_opener(base: str) -> urllib.request.OpenerDirector:
    """
    Login via POST /api/v4/users/login and return an opener that carries cookies.
    This supports deployments where personal access tokens are disabled.
    """
    username = env("MM_USERNAME")
    password = env("MM_PASSWORD")
    if not username or not password:
        raise RuntimeError("Missing MM_USERNAME or MM_PASSWORD for login auth")

    opener = _build_opener(token="")
    url = f"{base}/api/v4/users/login"
    payload = json.dumps({"login_id": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(req, timeout=60) as resp:
            _ = resp.read()  # body not needed; cookies are stored in the jar
            return opener
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Login failed: HTTP {e.code}: {body}") from e


def http_json(opener: urllib.request.OpenerDirector, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with opener.open(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def http_upload_bytes(opener: urllib.request.OpenerDirector, url: str, content: bytes) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        data=content,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(content)),
        },
        method="POST",
    )
    with opener.open(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return None
        return json.loads(raw)


def swift_connect():
    clouds = env("SWIFT_CLOUDS_YAML_PATH", env("OS_CLIENT_CONFIG_FILE", "clouds.yaml"))
    os.environ.setdefault("OS_CLIENT_CONFIG_FILE", clouds)
    cloud = env("SWIFT_CLOUD", env("OS_CLOUD", "openstack")) or "openstack"
    import openstack  # type: ignore

    return openstack.connect(cloud=cloud)


def main() -> int:
    base = env("MM_BASE_URL")
    channel_id = env("MM_CHANNEL_ID")
    if not base or not channel_id:
        print("Missing MM_BASE_URL or MM_CHANNEL_ID", file=sys.stderr)
        return 2

    token = env("MM_TOKEN")
    try:
        opener = _build_opener(token=token) if token else login_and_get_opener(base)
    except Exception as e:
        print(f"Auth failed: {e}", file=sys.stderr)
        return 2

    filename = env("MM_FILENAME", "swift_smoke.txt")
    content = env("MM_CONTENT", "hello swift").encode("utf-8")

    # 1) create upload session
    us = http_json(
        opener,
        "POST",
        f"{base}/api/v4/uploads",
        {"channel_id": channel_id, "filename": filename, "file_size": len(content)},
    )
    upload_id = us.get("id")
    if not upload_id:
        print(f"Could not create upload session. Response: {us}", file=sys.stderr)
        return 1

    # 2) upload bytes
    info = http_upload_bytes(opener, f"{base}/api/v4/uploads/{upload_id}", content)
    print(f"Uploaded via Mattermost. upload_id={upload_id} fileinfo_id={(info or {}).get('id')}")

    # 3) search Swift for replicated object
    container = env("SWIFT_CONTAINER")
    if not container:
        print("Missing SWIFT_CONTAINER", file=sys.stderr)
        return 2
    prefix = env("SWIFT_PREFIX", "mattermost").strip().strip("/")
    search_prefix = f"{prefix}/" if prefix else ""
    suffix = f"/{upload_id}/{filename}"

    conn = swift_connect()
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            found = None
            # Iterate objects under prefix; stop when we find a suffix match.
            for obj in conn.object_store.objects(container, prefix=search_prefix):
                name = getattr(obj, "name", "") or ""
                if name.endswith(suffix):
                    found = name
                    break
            if found:
                print(f"OK: found Swift object: {found}")
                return 0
            time.sleep(5)
        print(f"NOT FOUND in Swift after 120s. Looked for suffix: {suffix} under prefix: {search_prefix}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

