import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

TRANSIENT_ERROR_CODES = {
    "CONN_TIMEOUT",
    "HTTP_429",
    "HTTP_503",
    "BROWSER_NAVIGATION_TIMEOUT",
    "LLM_INVALID_RESPONSE",
}


class RecoverableError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SafetyError(Exception):
    """Raised when an operation would violate safety or retry policy."""


@dataclass
class RetryPolicy:
    max_retries: int = 2
    backoff_base_ms: int = 1000
    eligible_codes: frozenset[str] = frozenset(TRANSIENT_ERROR_CODES)
    is_idempotent: bool = True  # MUST be False for non-idempotent operations without key


async def with_retry(
    fn: Callable[..., Any],
    policy: RetryPolicy,
    *args: Any,
    **kwargs: Any,
) -> tuple[T, int]:
    """
    Executes an async function with bounded exponential backoff.
    Returns (result, retry_count).
    Enforces idempotency constraints.
    """
    retries = 0
    last_error: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            res = await fn(*args, **kwargs)
            return res, retries
        except RecoverableError as e:
            last_error = e
            if e.code not in policy.eligible_codes:
                raise
            if not policy.is_idempotent:
                raise SafetyError(
                    "Refusing to retry non-idempotent operation without an idempotency guarantee"
                )
            if attempt == policy.max_retries:
                raise
            retries += 1
            wait_seconds = (policy.backoff_base_ms * (2**attempt)) / 1000.0
            await asyncio.sleep(wait_seconds)
        except Exception:
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Unexpected retry loop termination")
