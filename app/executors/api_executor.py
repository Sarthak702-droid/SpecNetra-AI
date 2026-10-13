import time
from typing import Any

import httpx

from app.config import settings
from app.core.contract_validation import validate_response_schema
from app.core.recovery import RecoverableError
from app.core.security import assert_allowed_url
from app.core.state_manager import RunStateManager
from app.executors.assertions import assert_field, assert_status
from app.models import APIStep, StepResult


def extract_value_by_path(data: Any, path: str) -> Any:
    parts = path.split(".")
    curr = data
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
            curr = curr[int(part)]
        else:
            return None
    return curr


async def execute_api_step(
    step: APIStep,
    client: httpx.AsyncClient,
    state_manager: RunStateManager,
    step_index: int = 0,
) -> StepResult:
    path = step.path
    if "{" in path and "}" in path:
        resources = await state_manager.get_all_resources()
        for k, v in resources.items():
            path = path.replace(f"{{{k}}}", str(v))

    url = f"{settings.api_base_url.rstrip('/')}/{path.lstrip('/')}"
    assert_allowed_url(url)

    # Resolve token if authenticated session exists
    token = await state_manager.get_token("session_token")
    headers = dict(step.headers)
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"

    start_time = time.monotonic()
    response = None
    try:
        response = await client.request(
            method=step.method,
            url=url,
            json=step.body,
            headers=headers,
            timeout=settings.test_timeout_ms / 1000.0,
        )
    except httpx.ConnectTimeout as e:
        raise RecoverableError(code="CONN_TIMEOUT", message=f"Connection timed out: {e}")
    except httpx.ConnectError as e:
        raise RecoverableError(code="CONN_TIMEOUT", message=f"Connection failed: {e}")
    except Exception as e:
        duration_ms = (time.monotonic() - start_time) * 1000.0
        return StepResult(
            step_index=step_index,
            outcome="ERROR",
            observed=f"HTTP request error: {e!s}",
            duration_ms=duration_ms,
            error_code="HTTP_CLIENT_ERROR",
        )

    duration_ms = (time.monotonic() - start_time) * 1000.0

    # Rate limiting retry support
    if response.status_code == 429:
        raise RecoverableError(code="HTTP_429", message="Rate limited by server (HTTP 429)")
    if response.status_code == 503:
        raise RecoverableError(code="HTTP_503", message="Service unavailable (HTTP 503)")

    content_type = response.headers.get("content-type", "")
    body: Any = None
    if "application/json" in content_type:
        try:
            body = response.json()
        except Exception:
            body = None

    errors: list[str] = []

    # Check assertions strictly
    for assertion in step.assertions:
        kind = assertion.get("kind")
        if kind == "assert_status":
            res = assert_status(response.status_code, assertion.get("expected", 200))
            if not res.passed:
                errors.append(res.message)
        elif kind == "assert_json_schema":
            if body is None:
                errors.append(
                    f"Schema assertion failed: response is not valid JSON (content-type: {content_type})"
                )
            else:
                schema = assertion.get("schema", {})
                schema_errs = validate_response_schema(body, schema)
                errors.extend(schema_errs)
        elif kind == "assert_field":
            if body is None:
                errors.append(
                    f"Field assertion '{assertion.get('path')}' failed: response is not valid JSON (content-type: {content_type})"
                )
            else:
                res = assert_field(body, assertion.get("path", ""), assertion.get("expected"))
                if not res.passed:
                    errors.append(res.message)

    if errors:
        return StepResult(
            step_index=step_index,
            outcome="FAILED",
            observed="; ".join(errors),
            duration_ms=duration_ms,
            error_code="API_ASSERTION_FAILED",
        )

    # Commit state only AFTER all assertions have passed (transactional pattern)
    if body and isinstance(body, dict):
        if "access_token" in body:
            await state_manager.store_token("session_token", body["access_token"])

    if body and step.extract:
        for json_path, ref_key in step.extract.items():
            extracted_val = extract_value_by_path(body, json_path)
            if extracted_val is not None:
                await state_manager.store_resource(ref_key, extracted_val)

    return StepResult(
        step_index=step_index,
        outcome="PASSED",
        observed=f"HTTP {response.status_code} ({duration_ms:.1f}ms)",
        duration_ms=duration_ms,
    )
