import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "password",
    "token",
    "authorization",
    "secret",
    "cookie",
    "set-cookie",
    "access_token",
}


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_dict(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v
    return sanitized


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
            "test_id": getattr(record, "test_id", None),
            "agent": getattr(record, "agent", None),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        filtered = {k: v for k, v in data.items() if v is not None}
        return json.dumps(sanitize_dict(filtered))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    logging.root.setLevel(level)
    logging.root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
