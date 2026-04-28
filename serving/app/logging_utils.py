from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=True)


def get_logger(name: str = "serving") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


_audit_lock = Lock()


def _audit_log_path() -> str:
    path = os.environ.get("INFERENCE_EVENTS_LOG_PATH", "serving/logs/inference_events.jsonl").strip()
    return path or "serving/logs/inference_events.jsonl"


def log_inference_event(
    *,
    backend: str,
    status_code: int,
    latency_ms: float,
    toxicity_score: float | None,
    action: str | None,
    endpoint: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "backend": backend,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 3),
        "success": 200 <= status_code < 300,
        "toxicity_score": toxicity_score,
        "action": action,
    }
    if endpoint:
        payload["endpoint"] = endpoint
    if error:
        payload["error"] = error
    if extra:
        payload.update(extra)

    try:
        path = _audit_log_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with _audit_lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        # Best-effort only; observability must not break inference.
        pass
