from collections import defaultdict, deque

from app.models import TestCase


class SchedulerError(Exception):
    """Raised when test dependencies cannot be resolved or contain cycles."""


def topological_sort(tests: list[TestCase]) -> list[list[TestCase]]:
    """
    Groups tests into dependency batches that can execute in order.
    Detects missing dependencies and circular dependencies.
    """
    id_to_test = {t.test_id: t for t in tests}
    in_degree = defaultdict(int)
    dependents = defaultdict(list)

    # Initialize all tests with 0 in-degree
    for test in tests:
        if test.test_id not in in_degree:
            in_degree[test.test_id] = 0

    for test in tests:
        for dep in test.dependencies:
            if dep not in id_to_test:
                raise SchedulerError(f"Test '{test.test_id}' references unknown dependency '{dep}'")
            dependents[dep].append(test.test_id)
            in_degree[test.test_id] += 1

    queue = deque([t for t in tests if in_degree[t.test_id] == 0])
    batches: list[list[TestCase]] = []

    while queue:
        batch: list[TestCase] = []
        next_queue: deque[TestCase] = deque()
        while queue:
            t = queue.popleft()
            batch.append(t)
            for dep_id in dependents[t.test_id]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    next_queue.append(id_to_test[dep_id])
        batches.append(batch)
        queue = next_queue

    total_resolved = sum(len(b) for b in batches)
    if total_resolved != len(tests):
        raise SchedulerError("Circular dependency detected in test plan")

    return batches


def order_for_execution(tests: list[TestCase]) -> list[TestCase]:
    """Flat ordered list of tests respecting all dependencies."""
    batches = topological_sort(tests)
    return [t for batch in batches for t in batch]
