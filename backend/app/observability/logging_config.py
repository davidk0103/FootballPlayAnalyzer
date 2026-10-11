"""Structured JSON logging with request_id / job_id and redaction of sensitive fields."""

import json
import logging
import re
from datetime import UTC, datetime
from logging import LogRecord
from typing import Any

from app.observability.context import job_id_var, request_id_var

REDACT_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "authorization",
        "cookie",
        "jwt",
        "jwt_secret",
        "token",
        "secret",
        "api_key",
        "set-cookie",
    }
)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I)
GITHUB_PAT_RE = re.compile(r"github_pat_[A-Za-z0-9_]+")


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in REDACT_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        text = BEARER_RE.sub("Bearer [REDACTED]", value)
        return GITHUB_PAT_RE.sub("[REDACTED]", text)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _serialize(record: LogRecord) -> str:
    payload: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "msg": GITHUB_PAT_RE.sub("[REDACTED]", str(record.getMessage())),
    }
    rid = request_id_var.get()
    jid = job_id_var.get()
    if rid:
        payload["request_id"] = rid
    if jid:
        payload["job_id"] = jid
    if record.exc_info and record.exc_info[1]:
        payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        payload["exc"] = str(record.exc_info[1])
    for key, value in record.__dict__.items():
        if key.startswith("_") or key in {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "pathname",
            "filename",
            "module",
            "levelno",
            "levelname",
            "msecs",
            "message",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }:
            continue
        payload[key] = _redact_value(key, value)
    return json.dumps(payload, default=str)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        return _serialize(record)


def configure_logging(level: str = "INFO") -> None:
    """Root logger emits one JSON object per line. Uvicorn loggers follow the same format."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery"):
        log = logging.getLogger(name)
        log.handlers.clear()
        log.propagate = True
        log.setLevel(level.upper())
