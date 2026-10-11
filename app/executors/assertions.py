from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    passed: bool
    message: str


def assert_status(actual: int, expected: int) -> AssertionResult:
    passed = actual == expected
    msg = "" if passed else f"Status code mismatch: expected {expected}, got {actual}"
    return AssertionResult(passed=passed, message=msg)


def assert_field(body: dict[str, Any] | None, path: str, expected: Any = None) -> AssertionResult:
    if not isinstance(body, dict):
        return AssertionResult(
            passed=False, message=f"Expected JSON object, got {type(body).__name__}"
        )

    parts = path.split(".")
    curr: Any = body
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
            curr = curr[int(part)]
        else:
            return AssertionResult(
                passed=False, message=f"Field '{path}' not found in response body"
            )

    # If expected is None, check that curr is truthy / non-empty
    if expected is None:
        passed = curr is not None and curr != ""
        msg = "" if passed else f"Field '{path}' is empty or null"
        return AssertionResult(passed=passed, message=msg)

    passed = curr == expected
    msg = "" if passed else f"Field '{path}' value mismatch: expected {expected!r}, got {curr!r}"
    return AssertionResult(passed=passed, message=msg)


def assert_text(actual_text: str, expected_substring: str) -> AssertionResult:
    passed = expected_substring in actual_text
    msg = "" if passed else f"Text mismatch: '{expected_substring}' not found in '{actual_text}'"
    return AssertionResult(passed=passed, message=msg)


def assert_url(actual_url: str, expected_substring: str) -> AssertionResult:
    passed = expected_substring in actual_url
    msg = "" if passed else f"URL mismatch: expected '{expected_substring}' in '{actual_url}'"
    return AssertionResult(passed=passed, message=msg)
