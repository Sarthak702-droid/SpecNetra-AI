from typing import Any
from urllib.parse import urlparse

from app.config import settings

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "cookie",
    "set-cookie",
    "access_token",
    "secret",
}


class SecurityError(Exception):
    """Raised when an operation violates security policy."""


def is_allowed_host(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False
    # Check scheme - only http and https allowed
    if parsed.scheme not in ("http", "https"):
        return False
    return hostname in settings.allowed_target_hosts


def assert_allowed_url(url: str) -> None:
    if not is_allowed_host(url):
        raise SecurityError(f"Target host or scheme not permitted in allowlist: {url}")


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_KEYS:
            redacted[k] = REDACTED
        else:
            redacted[k] = v
    return redacted


def sanitize_for_prompt(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize dictionary data before sending to LLM prompts."""
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            continue  # do not even include sensitive keys in prompts
        if isinstance(v, dict):
            sanitized[k] = sanitize_for_prompt(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_for_prompt(i) if isinstance(i, dict) else i for i in v]
        else:
            sanitized[k] = v
    return sanitized
