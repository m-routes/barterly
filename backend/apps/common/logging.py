"""Structured logging: one JSON object per line, with the request id on every record.

Field names follow Cloud Logging's structured-log conventions (`severity`, `message`),
so Cloud Run parses levels and messages without an agent.
"""

import json
import logging
from datetime import UTC, datetime

from apps.common.request_context import get_request_id

# Attributes every LogRecord has; anything else came from `extra=` and is emitted.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}


class RequestIDFilter(logging.Filter):
    """Attach the request id (or '-') to every record.

    Django's `django.request` warnings for 4xx/5xx responses are written after the
    middleware has returned and cleared the context, but they carry the request in
    `extra={"request": ...}`, so the id is read from there first.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        request = getattr(record, "request", None)
        record.request_id = getattr(request, "request_id", None) or get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in vars(record).items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            if key == "request":
                # Log what identifies the request, not the object's repr.
                payload["method"] = getattr(value, "method", None)
                payload["path"] = getattr(value, "path", None)
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def logging_config(*, fmt: str = "json", level: str = "INFO") -> dict:
    """dictConfig for Django's LOGGING. fmt is 'json' (deployed) or 'plain' (local)."""
    if fmt not in {"json", "plain"}:
        raise ValueError(f"Unknown log format: {fmt!r}")
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": "apps.common.logging.RequestIDFilter"}},
        "formatters": {
            "json": {"()": "apps.common.logging.JsonFormatter"},
            "plain": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": fmt,
                "filters": ["request_id"],
            },
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Django logs every 4xx/5xx here; keep it, but don't duplicate to root handlers.
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }
