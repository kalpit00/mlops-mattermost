"""
Synthetic Mattermost-like message events + moderation labels for local/dev/staging.

**Message shape** aligns with Mattermost ``Post`` JSON (``create_at`` in milliseconds,
``user_id``, ``channel_id``, ``root_id``, ``message``, ``type``, etc.). See
``build_message_row``.

**Delivery**
- ``artifact`` (default): writes parquet/JSONL only under ``MLOPS_LOCAL_ARTIFACTS_ROOT``
  and optional S3/MinIO (``moderation-data`` bucket, ``nightly/{date}/`` keys).
- ``http``: POST each row to ``POST {base}/api/v4/posts`` with
  ``Authorization: Bearer <token>``. All posts use the **session user** from the
  token; ``synthetic_user_id`` in artifacts is for ML only. Threading: first post
  in a synthetic thread uses ``root_id: ""``; replies use the Mattermost id of the
  root post returned by the API.
- ``both``: artifact + HTTP.

**Backfilled ``create_at`` over HTTP** requires a token with *system admin*
(Mattermost clears ``create_at`` for non-admin users). Set
``MLOPS_SYNTHETIC_HTTP_SET_CREATE_AT=1`` and use an admin personal access token.

**Usage**
    python -m data.pipelines.cli_synthetic
    # or
    from data.pipelines.synthetic_messages import run_synthetic_message_generator
    run_synthetic_message_generator()
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

DeliveryMode = Literal["artifact", "http", "both"]


class SyntheticGeneratorError(Exception):
    pass


@dataclass
class SyntheticGeneratorConfig:
    """Rate, volume, and date range (env-overridable via ``from_env``)."""

    test_mode: bool = True
    seed: int = 42
    end_date: date = field(default_factory=lambda: date.today())
    n_days: int = 5
    messages_per_day: int = 120
    n_users: int = 80
    n_base_threads: int = 25
    min_messages_per_day: int = 50
    output_prefix: str = "nightly"
    local_artifacts_root: Path = field(default_factory=lambda: Path("data/artifacts"))
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = "admin"
    s3_secret_key: str = "admin12345"
    bucket: str = "moderation-data"
    s3_region: str = "us-east-1"
    skip_s3_upload: bool = False
    parquet_engine: str = "auto"
    delivery_mode: DeliveryMode = "artifact"
    http_base_url: str = ""
    http_token: str = ""
    http_channel_id: str = ""
    http_min_interval_sec: float = 0.0
    http_set_create_at: bool = False
    http_fail_fast: bool = False
    write_jsonl: bool = True
    write_combined_labeled_copy: bool = True

    @property
    def synthetic_root(self) -> Path:
        return self.local_artifacts_root / "synthetic"

    @classmethod
    def from_env(cls, **overrides: Any) -> SyntheticGeneratorConfig:
        def _b(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        def _i(name: str, default: int) -> int:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return int(v)

        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None or v.strip() == "":
                return default
            return float(v)

        _lar = os.environ.get("MLOPS_LOCAL_ARTIFACTS_ROOT")
        if _lar is None or not str(_lar).strip():
            _lar = "data/artifacts"
        root = Path(_lar).expanduser()

        test_mode = _b("MLOPS_SYNTHETIC_TEST_MODE", True)
        msg_day = _i("MLOPS_SYNTHETIC_MESSAGES_PER_DAY", 120 if test_mode else 1000)
        n_users = _i("MLOPS_SYNTHETIC_N_USERS", 80 if test_mode else 250)
        n_threads = _i("MLOPS_SYNTHETIC_N_BASE_THREADS", 25 if test_mode else 180)

        end_s = os.environ.get("MLOPS_SYNTHETIC_END_DATE")
        if end_s:
            end_d = date.fromisoformat(end_s.strip())
        else:
            end_d = date.today()

        mode_s = os.environ.get("MLOPS_SYNTHETIC_DELIVERY_MODE", "artifact").lower()
        if mode_s not in ("artifact", "http", "both"):
            mode_s = "artifact"

        cfg = cls(
            test_mode=test_mode,
            seed=_i("MLOPS_SYNTHETIC_SEED", 42),
            end_date=end_d,
            n_days=_i("MLOPS_SYNTHETIC_N_DAYS", 5),
            messages_per_day=msg_day,
            n_users=n_users,
            n_base_threads=n_threads,
            min_messages_per_day=_i("MLOPS_SYNTHETIC_MIN_MESSAGES_PER_DAY", 50),
            output_prefix=os.environ.get(
                "MLOPS_SYNTHETIC_OUTPUT_PREFIX", "nightly"
            ).strip("/"),
            local_artifacts_root=root,
            s3_endpoint=os.environ.get("MLOPS_S3_ENDPOINT", "http://127.0.0.1:9000"),
            s3_access_key=os.environ.get("MLOPS_S3_ACCESS_KEY", "admin"),
            s3_secret_key=os.environ.get("MLOPS_S3_SECRET_KEY", "admin12345"),
            bucket=os.environ.get("MLOPS_S3_BUCKET", "moderation-data"),
            s3_region=os.environ.get("MLOPS_S3_REGION", "us-east-1"),
            skip_s3_upload=_b("MLOPS_SYNTHETIC_SKIP_S3_UPLOAD", False)
            or _b("MLOPS_SKIP_S3_UPLOAD", False),
            parquet_engine=os.environ.get("MLOPS_PARQUET_ENGINE", "auto").lower(),
            delivery_mode=mode_s,  # type: ignore[assignment]
            http_base_url=os.environ.get("MLOPS_MM_BASE_URL", "").rstrip("/"),
            http_token=os.environ.get("MLOPS_MM_TOKEN", ""),
            http_channel_id=os.environ.get("MLOPS_MM_CHANNEL_ID", ""),
            http_min_interval_sec=_f("MLOPS_SYNTHETIC_HTTP_MIN_INTERVAL_SEC", 0.0),
            http_set_create_at=_b("MLOPS_SYNTHETIC_HTTP_SET_CREATE_AT", False),
            http_fail_fast=_b("MLOPS_SYNTHETIC_HTTP_FAIL_FAST", False),
            write_jsonl=_b("MLOPS_SYNTHETIC_WRITE_JSONL", True),
            write_combined_labeled_copy=_b(
                "MLOPS_SYNTHETIC_WRITE_COMBINED", True
            ),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                if k == "local_artifacts_root":
                    setattr(cfg, k, Path(v).expanduser())
                elif k == "end_date" and isinstance(v, str):
                    setattr(cfg, k, date.fromisoformat(v))
                else:
                    setattr(cfg, k, v)
        return cfg


@dataclass
class SyntheticGeneratorResult:
    total_messages: int
    days_written: list[str]
    message_paths: list[Path]
    label_paths: list[Path]
    jsonl_message_paths: list[Path]
    jsonl_label_paths: list[Path]
    combined_paths: list[Path]
    s3_keys_uploaded: list[str]
    http_posts_succeeded: int
    http_errors: list[str]


NEUTRAL_TEMPLATES = [
    "Can someone review this PR today?",
    "Please update the deployment notes.",
    "Meeting moved to 3 PM.",
    "I pushed the latest changes.",
    "Can you check the logs?",
    "Thanks for the help.",
    "Let's sync after lunch.",
    "The build passed on staging.",
    "Please add this to the backlog.",
    "I am looking into the bug now.",
    "Can someone verify the config?",
    "Please re-run the tests.",
]

AMBIGUOUS_TEMPLATES = [
    "This is getting out of hand.",
    "What is wrong with this thread?",
    "This makes no sense.",
    "You need to fix this.",
    "This is a mess.",
    "I cannot believe this happened again.",
    "This was not handled well.",
    "This is pretty bad.",
]

TOXIC_TEMPLATES = [
    "You are useless.",
    "This is a stupid idea.",
    "Shut up already.",
    "What a dumb change.",
    "This is complete garbage.",
    "You clearly do not know what you are doing.",
    "This is the worst thing I have seen today.",
    "Stop wasting everyone's time.",
]

CHANNEL_TYPES = ["public", "private", "direct", "group"]
CHANNEL_PROBS = [0.50, 0.20, 0.20, 0.10]


def _fake_channel_id(channel_type: str) -> str:
    """Stable 26-char id so parquet joins are deterministic (not real MM channels)."""
    h = hashlib.sha1(f"sim-channel:{channel_type}".encode()).hexdigest()
    return h[:26]


def _resolve_parquet_engine(preferred: str) -> str:
    if preferred == "pyarrow":
        return "pyarrow"
    if preferred == "fastparquet":
        return "fastparquet"
    try:
        import pyarrow  # noqa: F401

        return "pyarrow"
    except ImportError:
        pass
    try:
        import fastparquet  # noqa: F401

        return "fastparquet"
    except ImportError as e:
        raise SyntheticGeneratorError(
            "Install pyarrow or fastparquet to write parquet."
        ) from e


def _make_s3(cfg: SyntheticGeneratorConfig):
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name=cfg.s3_region,
    )


def _s3_put_bytes(
    client, bucket: str, key: str, data: bytes, content_type: str
) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def hash_user(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def make_thread_id(day_str: str, i: int) -> str:
    return f"thread_{day_str}_{i:04d}"


def choose_daily_counts(
    day_idx: int, messages_per_day: int, test_mode: bool, min_messages: int
) -> int:
    base = messages_per_day
    weekendish_adjust = -40 if day_idx in [0] and not test_mode else 0
    jitter = (
        np.random.randint(-15, 16)
        if test_mode
        else np.random.randint(-80, 81)
    )
    return max(min_messages, base + weekendish_adjust + jitter)


def pick_message_text(moderation_label: str) -> str:
    if moderation_label == "non_toxic":
        return random.choice(NEUTRAL_TEMPLATES)
    if moderation_label == "toxic":
        return random.choice(TOXIC_TEMPLATES)
    return random.choice(AMBIGUOUS_TEMPLATES)


def generate_day_events(
    day: date,
    day_idx: int,
    cfg: SyntheticGeneratorConfig,
    user_ids: list[str],
    high_risk_users: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (message_rows, label_rows) for one calendar day."""
    day_str = day.isoformat()
    n_messages = choose_daily_counts(
        day_idx, cfg.messages_per_day, cfg.test_mode, cfg.min_messages_per_day
    )
    thread_ids = [make_thread_id(day_str, i) for i in range(cfg.n_base_threads)]
    power_users = set(random.sample(user_ids, k=max(4, cfg.n_users // 12)))

    message_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []

    generated_at = datetime.now(timezone.utc).isoformat()

    for _ in range(n_messages):
        if random.random() < 0.35:
            user_id = random.choice(list(power_users))
        else:
            user_id = random.choice(user_ids)

        is_high_risk = user_id in high_risk_users

        if random.random() < 0.82:
            syn_thread_id = random.choice(thread_ids)
        else:
            syn_thread_id = make_thread_id(day_str, cfg.n_base_threads + len(message_rows))

        created_dt = datetime.combine(
            day, datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(seconds=int(np.random.randint(0, 24 * 60 * 60)))

        channel_type = str(np.random.choice(CHANNEL_TYPES, p=CHANNEL_PROBS))
        reviewed = random.random() < 0.68

        if is_high_risk and channel_type in ("public", "group"):
            label_probs = [0.42, 0.38, 0.20]
        elif is_high_risk:
            label_probs = [0.50, 0.28, 0.22]
        elif channel_type == "direct":
            label_probs = [0.82, 0.07, 0.11]
        else:
            label_probs = [0.76, 0.11, 0.13]

        moderation_label = str(
            np.random.choice(
                ["non_toxic", "toxic", "ambiguous"], p=label_probs
            )
        )
        final_label = moderation_label if reviewed else None
        message_text = pick_message_text(moderation_label)

        event_id = str(uuid.uuid4())
        create_at_ms = int(created_dt.timestamp() * 1000)

        msg = build_message_row(
            event_id=event_id,
            create_at_ms=create_at_ms,
            synthetic_user_id=user_id,
            channel_type=channel_type,
            message=message_text,
            root_id="",
            cfg=cfg,
        )
        msg["synthetic_thread_id"] = syn_thread_id
        msg["event_date"] = day_str
        message_rows.append(msg)

        label_rows.append(
            {
                "event_id": event_id,
                "synthetic_thread_id": syn_thread_id,
                "synthetic_user_id": user_id,
                "user_hash": hash_user(user_id),
                "channel_type": channel_type,
                "reviewed": reviewed,
                "moderation_label": final_label,
                "event_date": day_str,
                "generated_at": generated_at,
            }
        )

    return message_rows, label_rows


def build_message_row(
    *,
    event_id: str,
    create_at_ms: int,
    synthetic_user_id: str,
    channel_type: str,
    message: str,
    root_id: str,
    cfg: SyntheticGeneratorConfig,
    mattermost_post_id: str = "",
) -> dict[str, Any]:
    """
    Mattermost Post-shaped row for API/parquet (snake_case JSON field names).
    ``id`` is the synthetic event id until HTTP returns a server id.
    """
    ch_id = _fake_channel_id(channel_type)
    if cfg.http_channel_id and cfg.delivery_mode in ("http", "both"):
        ch_id = cfg.http_channel_id

    post_id = mattermost_post_id or event_id
    return {
        "event_id": event_id,
        "id": post_id,
        "create_at": create_at_ms,
        "update_at": create_at_ms,
        "edit_at": 0,
        "delete_at": 0,
        "is_pinned": False,
        "user_id": synthetic_user_id,
        "channel_id": ch_id,
        "root_id": root_id,
        "original_id": "",
        "message": message,
        "type": "",
        "props": {},
        "hashtags": "",
        "file_ids": [],
        "pending_post_id": "",
        "remote_id": None,
        "reply_count": 0,
        "last_reply_at": 0,
    }


def assign_thread_root_ids(message_df: pd.DataFrame) -> pd.DataFrame:
    """First row per synthetic_thread_id gets root_id ''; later rows point to first id."""
    df = message_df.sort_values(["create_at", "event_id"]).copy()
    root_id_by_thread: dict[str, str] = {}
    new_roots: list[str] = []
    for _, row in df.iterrows():
        tid = row["synthetic_thread_id"]
        pid = row["id"]
        if tid not in root_id_by_thread:
            root_id_by_thread[tid] = pid
            new_roots.append("")
        else:
            new_roots.append(root_id_by_thread[tid])
    df["root_id"] = new_roots
    return df


def remap_root_ids_after_http(df: pd.DataFrame) -> pd.DataFrame:
    """Reply ``root_id`` values point at the root post's former synthetic id (= its event_id)."""
    ev_to_mid = df.set_index("event_id")["id"].astype(str).to_dict()
    out = df.copy()

    def _map_root(rid: Any) -> str:
        if rid is None or str(rid) == "":
            return ""
        return ev_to_mid.get(str(rid), str(rid))

    out["root_id"] = out["root_id"].map(_map_root)
    return out


def post_to_mattermost(
    base_url: str,
    token: str,
    body: dict[str, Any],
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    url = f"{base_url}/api/v4/posts"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise SyntheticGeneratorError(
            f"HTTP {e.code} posting to Mattermost: {err_body}"
        ) from e


def deliver_http_all(
    df_messages: pd.DataFrame,
    cfg: SyntheticGeneratorConfig,
) -> tuple[pd.DataFrame, int, list[str]]:
    """Post in global chronological order; update ``id`` from server per event_id."""
    if cfg.delivery_mode not in ("http", "both"):
        out = df_messages.copy()
        out["mattermost_post_id"] = out["id"]
        return out, 0, []

    if not cfg.http_base_url or not cfg.http_token or not cfg.http_channel_id:
        raise SyntheticGeneratorError(
            "HTTP delivery requires MLOPS_MM_BASE_URL, MLOPS_MM_TOKEN, MLOPS_MM_CHANNEL_ID"
        )

    order = df_messages.sort_values(["create_at", "event_id"])
    thread_to_root_mm_id: dict[str, str] = {}
    errors: list[str] = []
    ok = 0
    id_by_event: dict[str, str] = {}

    last_call = 0.0

    for _, row in order.iterrows():
        if cfg.http_min_interval_sec > 0:
            elapsed = time.monotonic() - last_call
            if elapsed < cfg.http_min_interval_sec:
                time.sleep(cfg.http_min_interval_sec - elapsed)
            last_call = time.monotonic()

        ev = row["event_id"]
        tid = row["synthetic_thread_id"]
        root_mm = thread_to_root_mm_id.get(tid, "")

        body: dict[str, Any] = {
            "channel_id": cfg.http_channel_id,
            "message": row["message"],
            "root_id": root_mm,
            "type": row["type"] or "",
        }
        if cfg.http_set_create_at:
            body["create_at"] = int(row["create_at"])

        try:
            resp = post_to_mattermost(cfg.http_base_url, cfg.http_token, body)
            mm_id = resp.get("id", "") or row["id"]
            id_by_event[ev] = mm_id
            if tid not in thread_to_root_mm_id:
                thread_to_root_mm_id[tid] = mm_id
            ok += 1
        except SyntheticGeneratorError as e:
            errors.append(str(e))
            id_by_event[ev] = row["id"]
            if cfg.http_fail_fast:
                raise
        except OSError as e:
            errors.append(str(e))
            id_by_event[ev] = row["id"]
            if cfg.http_fail_fast:
                raise SyntheticGeneratorError(str(e)) from e

    out = df_messages.copy()
    out["id"] = out["event_id"].map(id_by_event).fillna(out["id"])
    out["mattermost_post_id"] = out["id"]
    return out, ok, errors


def run_synthetic_message_generator(
    *,
    config: Optional[SyntheticGeneratorConfig] = None,
) -> SyntheticGeneratorResult:
    """
    Generate synthetic messages (Post-shaped) and separate moderation label rows,
    write per-day parquet (+ optional JSONL), upload to shared object storage layout.
    """
    cfg = config or SyntheticGeneratorConfig.from_env()
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    parquet_engine = _resolve_parquet_engine(cfg.parquet_engine)
    s3_keys: list[str] = []
    msg_paths: list[Path] = []
    label_paths: list[Path] = []
    jmsg_paths: list[Path] = []
    jlabel_paths: list[Path] = []
    combined_paths: list[Path] = []
    days_written: list[str] = []
    http_ok = 0
    http_errs: list[str] = []

    if cfg.delivery_mode in ("http", "both"):
        if not cfg.http_base_url or not cfg.http_token or not cfg.http_channel_id:
            raise SyntheticGeneratorError(
                "delivery_mode http/both requires http_base_url, http_token, http_channel_id"
            )

    user_ids = [f"user_{i:03d}" for i in range(cfg.n_users)]
    high_risk_users = set(random.sample(user_ids, k=max(5, cfg.n_users // 10)))

    all_msg_rows: list[dict[str, Any]] = []
    all_label_rows: list[dict[str, Any]] = []

    for day_idx in range(cfg.n_days):
        day = cfg.end_date - timedelta(days=day_idx)
        mrows, lrows = generate_day_events(
            day, day_idx, cfg, user_ids, high_risk_users
        )
        all_msg_rows.extend(mrows)
        all_label_rows.extend(lrows)

    if not all_msg_rows:
        return SyntheticGeneratorResult(
            0, [], [], [], [], [], [], [], 0, []
        )

    df_msg = pd.DataFrame(all_msg_rows)
    df_msg = assign_thread_root_ids(df_msg)

    df_label = pd.DataFrame(all_label_rows)

    if cfg.delivery_mode in ("http", "both"):
        df_msg, http_ok, http_errs = deliver_http_all(df_msg, cfg)
        df_msg = remap_root_ids_after_http(df_msg)
        id_map = df_msg.set_index("event_id")["id"].astype(str).to_dict()
        df_label["mattermost_post_id"] = df_label["event_id"].map(id_map)
    else:
        df_msg["mattermost_post_id"] = df_msg["id"]
        df_label["mattermost_post_id"] = df_label["event_id"].map(
            df_msg.set_index("event_id")["id"].astype(str)
        )

    s3_client = None
    if not cfg.skip_s3_upload:
        s3_client = _make_s3(cfg)

    for day_idx in range(cfg.n_days):
        day = cfg.end_date - timedelta(days=day_idx)
        day_str = day.isoformat()
        sub = df_msg[df_msg["event_date"] == day_str]
        sub_labels = df_label[df_label["event_date"] == day_str]

        if sub.empty:
            continue

        days_written.append(day_str)
        day_dir = cfg.synthetic_root / cfg.output_prefix / day_str
        day_dir.mkdir(parents=True, exist_ok=True)

        msg_out = sub.drop(
            columns=["synthetic_thread_id", "event_date"], errors="ignore"
        ).copy()
        label_out = sub_labels.drop(columns=["event_date"], errors="ignore").copy()

        if "props" in msg_out.columns:
            msg_out["props"] = msg_out["props"].apply(
                lambda x: json.dumps(x) if isinstance(x, dict) else x
            )

        mp = day_dir / "messages.parquet"
        lp = day_dir / "moderation_labels.parquet"
        msg_out.to_parquet(mp, index=False, engine=parquet_engine)
        label_out.to_parquet(lp, index=False, engine=parquet_engine)
        msg_paths.append(mp)
        label_paths.append(lp)

        jm = jl = None
        if cfg.write_jsonl:
            jm = day_dir / "messages.jsonl"
            jl = day_dir / "moderation_labels.jsonl"
            jm.write_text(
                "\n".join(json.dumps(x) for x in msg_out.to_dict("records"))
                + "\n",
                encoding="utf-8",
            )
            jl.write_text(
                "\n".join(json.dumps(x) for x in label_out.to_dict("records"))
                + "\n",
                encoding="utf-8",
            )
            jmsg_paths.append(jm)
            jlabel_paths.append(jl)

        if cfg.write_combined_labeled_copy:
            lb = label_out.drop(
                columns=["mattermost_post_id"],
                errors="ignore",
            )
            combined = msg_out.merge(lb, on="event_id", how="inner")
            cp = day_dir / "labeled_messages.parquet"
            combined.to_parquet(cp, index=False, engine=parquet_engine)
            combined_paths.append(cp)

        prefix = f"{cfg.output_prefix}/{day_str}"
        if s3_client:
            for local_path, name in (
                (mp, "messages.parquet"),
                (lp, "moderation_labels.parquet"),
            ):
                key = f"{prefix}/{name}"
                s3_client.upload_file(str(local_path), cfg.bucket, key)
                s3_keys.append(key)
            if cfg.write_jsonl and jm is not None and jl is not None:
                for local_path, name in (
                    (jm, "messages.jsonl"),
                    (jl, "moderation_labels.jsonl"),
                ):
                    key = f"{prefix}/{name}"
                    s3_client.upload_file(str(local_path), cfg.bucket, key)
                    s3_keys.append(key)
            if cfg.write_combined_labeled_copy and combined_paths:
                key = f"{prefix}/labeled_messages.parquet"
                s3_client.upload_file(str(combined_paths[-1]), cfg.bucket, key)
                s3_keys.append(key)

    return SyntheticGeneratorResult(
        total_messages=len(df_msg),
        days_written=days_written,
        message_paths=msg_paths,
        label_paths=label_paths,
        jsonl_message_paths=jmsg_paths,
        jsonl_label_paths=jlabel_paths,
        combined_paths=combined_paths,
        s3_keys_uploaded=s3_keys,
        http_posts_succeeded=http_ok,
        http_errors=http_errs,
    )
