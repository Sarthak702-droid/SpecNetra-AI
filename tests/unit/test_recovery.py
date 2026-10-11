import pytest

from app.core.recovery import (
    RecoverableError,
    RetryPolicy,
    SafetyError,
    with_retry,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    attempts = 0

    async def flaky_call():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RecoverableError(code="CONN_TIMEOUT", message="Timeout")
        return "SUCCESS"

    policy = RetryPolicy(max_retries=2, backoff_base_ms=10, is_idempotent=True)
    res, retries = await with_retry(flaky_call, policy)
    assert res == "SUCCESS"
    assert retries == 1
    assert attempts == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_fails_after_max_retries():
    attempts = 0

    async def always_failing():
        nonlocal attempts
        attempts += 1
        raise RecoverableError(code="CONN_TIMEOUT", message="Always timeout")

    policy = RetryPolicy(max_retries=2, backoff_base_ms=5, is_idempotent=True)
    with pytest.raises(RecoverableError):
        await with_retry(always_failing, policy)
    assert attempts == 3  # initial + 2 retries


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_idempotent_refuses_retry():
    attempts = 0

    async def non_idempotent_call():
        nonlocal attempts
        attempts += 1
        raise RecoverableError(code="CONN_TIMEOUT", message="Timeout on POST")

    policy = RetryPolicy(max_retries=2, backoff_base_ms=5, is_idempotent=False)
    with pytest.raises(SafetyError, match="Refusing to retry non-idempotent operation"):
        await with_retry(non_idempotent_call, policy)
    assert attempts == 1  # must not retry
