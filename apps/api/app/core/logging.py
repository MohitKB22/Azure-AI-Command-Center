"""Structured JSON logging with request/correlation IDs and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SECRET_KEY_HINTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "connection_string",
    "client_secret",
)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+"),
    re.compile(r"(?i)(sk-[a-z0-9]{8,})"),
    re.compile(r"(?i)(AccountKey=)[^;]+"),
]

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def redact(value: Any) -> Any:
    """Recursively strip anything that looks like a credential."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(hint in str(key).lower() for hint in _SECRET_KEY_HINTS):
                out[key] = "***redacted***"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for pattern in _SECRET_VALUE_PATTERNS:
            value = pattern.sub(r"\1***redacted***", value)
        return value
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id_ctx.get():
            payload["request_id"] = request_id_ctx.get()
        if correlation_id_ctx.get():
            payload["correlation_id"] = correlation_id_ctx.get()
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            payload.update(redact(extras))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).handlers = [handler]
        logging.getLogger(noisy).propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
