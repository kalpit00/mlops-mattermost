from __future__ import annotations

import json
import logging
import os
import sys
import time
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


def get_audit_logger(name: str = "serving.audit") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    path = os.environ.get("INFERENCE_AUDIT_LOG_PATH", "/tmp/inference_requests.jsonl").strip() or "/tmp/inference_requests.jsonl"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_inference_event(
    *,
    runtime: str,
    endpoint: str,
    status_code: int,
    latency_ms: float,
    model_version: str,
    policy_action: str | None = None,
    degraded: bool = False,
    text_length: int | None = None,
    scenario: str | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "runtime": runtime,
        "endpoint": endpoint,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 3),
        "model_version": model_version,
        "degraded": degraded,
    }
    if policy_action is not None:
        payload["policy_action"] = policy_action
    if text_length is not None:
        payload["text_length"] = text_length
    if scenario:
        payload["scenario"] = scenario
    if error:
        payload["error"] = error

    get_audit_logger().info("inference_request", extra={"extra": payload})
