from typing import Any

import httpx

from app.core.logging import get_logger
from app.core.recovery import RetryPolicy, with_retry
from app.core.state_manager import get_run_state_manager
from app.core.test_scheduler import order_for_execution
from app.executors.api_executor import execute_api_step
from app.models import APIStep, RunState, StepResult, TestResult

logger = get_logger(__name__)


async def execute_api_node(state: RunState) -> dict[str, Any]:
    plan = state.get("test_plan")
    if not plan:
        return {"errors": ["No test plan found for API execution"]}

    ordered_tests = order_for_execution(plan.tests)
    run_id = state["run_id"]
    state_manager = get_run_state_manager(run_id)

    test_results: list[TestResult] = []

    async with httpx.AsyncClient() as client:
        for test in ordered_tests:
            api_steps = [
                s
                for s in test.steps
                if isinstance(s, APIStep) or getattr(s, "kind", None) == "api_request"
            ]
            ui_steps = [s for s in test.steps if getattr(s, "kind", None) == "ui_action"]

            # If it's a UI-only test, skip in API specialist (UI specialist will run it)
            if not api_steps and ui_steps:
                continue

            step_results: list[StepResult] = []
            test_outcome = "PASSED"
            total_duration = 0.0
            error_code = None
            observed_msgs = []
            total_retries = 0

            for idx, step in enumerate(api_steps):
                policy = RetryPolicy(
                    max_retries=test.max_retries,
                    is_idempotent=(step.method in ("GET", "PUT", "DELETE", "HEAD")),
                )
                try:
                    step_res, retries = await with_retry(
                        execute_api_step,
                        policy,
                        step,
                        client,
                        state_manager,
                        step_index=idx,
                    )
                    total_retries += retries
                except Exception as e:
                    step_res = StepResult(
                        step_index=idx,
                        outcome="ERROR",
                        observed=f"Step failed after retries: {e}",
                        duration_ms=0.0,
                        error_code="STEP_EXECUTION_ERROR",
                    )

                step_results.append(step_res)
                total_duration += step_res.duration_ms
                observed_msgs.append(step_res.observed)

                if step_res.outcome in ("FAILED", "ERROR"):
                    test_outcome = step_res.outcome
                    error_code = step_res.error_code
                    break

            # If there are UI steps for this test, we don't finalize the test result here
            # if API passed; UI Specialist will execute UI steps and finalize.
            # But if API failed, the whole test failed right here!
            if test_outcome in ("FAILED", "ERROR") or not ui_steps:
                test_results.append(
                    TestResult(
                        test_id=test.test_id,
                        requirement_ids=test.requirement_ids,
                        outcome=test_outcome,  # type: ignore
                        expected=test.expected,
                        observed="; ".join(observed_msgs),
                        step_results=step_results,
                        duration_ms=total_duration,
                        retry_count=total_retries,
                        error_code=error_code,
                    )
                )

    return {"test_results": test_results}
