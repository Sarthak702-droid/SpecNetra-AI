import pytest

from app.core.test_scheduler import check_dependency_status
from app.models import APIStep, TestCase


@pytest.mark.unit
def test_dependency_blocking_when_prereq_fails():
    _ = TestCase(
        test_id="T1",
        requirement_ids=["REQ-1"],
        priority="P0",
        category="api",
        steps=[APIStep(operation_id="op1", method="GET", path="/test")],
        expected="Op 1 succeeds",
    )
    t2 = TestCase(
        test_id="T2",
        requirement_ids=["REQ-1"],
        priority="P0",
        category="api",
        dependencies=["T1"],
        steps=[APIStep(operation_id="op2", method="GET", path="/test2")],
        expected="Op 2 succeeds",
    )

    # 1. T1 PASSED -> T2 is runnable
    outcomes_passed = {"T1": "PASSED"}
    is_blocked, reason = check_dependency_status(t2, outcomes_passed)
    assert is_blocked is False
    assert reason is None

    # 2. T1 FAILED -> T2 must be BLOCKED
    outcomes_failed = {"T1": "FAILED"}
    is_blocked, reason = check_dependency_status(t2, outcomes_failed)
    assert is_blocked is True
    assert "had outcome 'FAILED'" in reason

    # 3. T1 ERROR -> T2 must be BLOCKED
    outcomes_error = {"T1": "ERROR"}
    is_blocked, reason = check_dependency_status(t2, outcomes_error)
    assert is_blocked is True
    assert "had outcome 'ERROR'" in reason

    # 4. T1 unexecuted -> T2 must be BLOCKED
    outcomes_unexecuted = {}
    is_blocked, reason = check_dependency_status(t2, outcomes_unexecuted)
    assert is_blocked is True
    assert "has not executed yet" in reason
