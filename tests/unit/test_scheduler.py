import pytest

from app.core.test_scheduler import SchedulerError, order_for_execution, topological_sort
from app.models import APIStep, TestCase


def make_dummy_test(test_id: str, deps: list[str]) -> TestCase:
    return TestCase(
        test_id=test_id,
        requirement_ids=["REQ-001"],
        priority="P0",
        category="api",
        dependencies=deps,
        steps=[APIStep(operation_id="dummy", method="GET", path="/dummy")],
        expected="Expected success",
    )


@pytest.mark.unit
def test_topological_sort_order():
    t1 = make_dummy_test("T1", [])
    t2 = make_dummy_test("T2", ["T1"])
    t3 = make_dummy_test("T3", ["T2"])

    ordered = order_for_execution([t3, t1, t2])
    ordered_ids = [t.test_id for t in ordered]
    assert ordered_ids == ["T1", "T2", "T3"]


@pytest.mark.unit
def test_circular_dependency_raises():
    t1 = make_dummy_test("T1", ["T2"])
    t2 = make_dummy_test("T2", ["T1"])

    with pytest.raises(SchedulerError, match="Circular dependency"):
        topological_sort([t1, t2])


@pytest.mark.unit
def test_unknown_dependency_raises():
    t1 = make_dummy_test("T1", ["NON_EXISTENT"])

    with pytest.raises(SchedulerError, match="unknown dependency"):
        topological_sort([t1])
