import pytest
from pydantic import ValidationError

from app.models import APIStep, TestCase, TestPlan, UIStep


@pytest.mark.unit
def test_testcase_requires_requirement_ids():
    with pytest.raises(ValidationError):
        TestCase(
            test_id="T1",
            requirement_ids=[],  # must be min_length=1
            priority="P0",
            category="api",
            steps=[],
            expected="Should fail validation",
        )


@pytest.mark.unit
def test_testcase_valid():
    tc = TestCase(
        test_id="T1",
        requirement_ids=["REQ-001"],
        priority="P0",
        category="api",
        steps=[
            APIStep(
                operation_id="loginUser",
                method="POST",
                path="/api/auth/login",
            )
        ],
        expected="Valid login",
    )
    assert tc.test_id == "T1"
    assert len(tc.steps) == 1


@pytest.mark.unit
def test_testplan_bounds():
    tc = TestCase(
        test_id="T1",
        requirement_ids=["REQ-001"],
        priority="P0",
        category="ui",
        steps=[UIStep(action="navigate", params={"url": "http://localhost:3000"})],
        expected="Homepage loads",
    )
    # Empty tests list should fail
    with pytest.raises(ValidationError):
        TestPlan(plan_id="p1", tests=[])

    plan = TestPlan(plan_id="p1", tests=[tc])
    assert len(plan.tests) == 1
