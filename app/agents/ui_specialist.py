from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from app.config import settings
from app.core.logging import get_logger
from app.core.recovery import RetryPolicy, with_retry
from app.core.state_manager import get_run_state_manager
from app.core.test_scheduler import order_for_execution
from app.executors.browser_executor import execute_ui_step
from app.models import RunState, StepResult, TestResult

logger = get_logger(__name__)


async def execute_ui_node(state: RunState) -> dict[str, Any]:
    plan = state.get("test_plan")
    if not plan:
        return {"errors": ["No test plan found for UI execution"]}

    ordered_tests = order_for_execution(plan.tests)
    run_id = state["run_id"]
    state_manager = get_run_state_manager(run_id)
    output_dir = Path(settings.output_dir)

    existing_results = {r.test_id: r for r in state.get("test_results", [])}
    new_results: list[TestResult] = []
    evidence_manifest: list[dict[str, Any]] = []

    tests_with_ui = [
        t for t in ordered_tests if any(getattr(s, "kind", None) == "ui_action" for s in t.steps)
    ]

    if not tests_with_ui:
        return {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.browser_headless)
        context = await browser.new_context()
        page = await context.new_page()

        for test in tests_with_ui:
            # If earlier API step already failed this test, don't execute UI steps
            if test.test_id in existing_results and existing_results[test.test_id].outcome in (
                "FAILED",
                "ERROR",
            ):
                continue

            ui_steps = [s for s in test.steps if getattr(s, "kind", None) == "ui_action"]
            step_results: list[StepResult] = []
            test_outcome = "PASSED"
            total_duration = 0.0
            error_code = None
            observed_msgs = []
            test_evidence: list[str] = []
            total_retries = 0

            for idx, step in enumerate(ui_steps):
                policy = RetryPolicy(max_retries=test.max_retries, is_idempotent=True)
                try:
                    step_res, retries = await with_retry(
                        execute_ui_step,
                        policy,
                        step,
                        page,
                        state_manager,
                        output_dir,
                        test.test_id,
                        step_index=idx,
                    )
                    total_retries += retries
                except Exception as e:
                    step_res = StepResult(
                        step_index=idx,
                        outcome="ERROR",
                        observed=f"UI step exception: {e}",
                        duration_ms=0.0,
                        error_code="STEP_EXECUTION_ERROR",
                    )

                step_results.append(step_res)
                total_duration += step_res.duration_ms
                observed_msgs.append(step_res.observed)
                if step_res.evidence_ids:
                    test_evidence.extend(step_res.evidence_ids)

                if step_res.outcome in ("FAILED", "ERROR"):
                    test_outcome = step_res.outcome
                    error_code = step_res.error_code
                    break

            for ev in test_evidence:
                evidence_manifest.append(
                    {
                        "test_id": test.test_id,
                        "path": ev,
                        "kind": "screenshot" if ev.endswith(".png") else "trace",
                    }
                )

            new_results.append(
                TestResult(
                    test_id=test.test_id,
                    requirement_ids=test.requirement_ids,
                    outcome=test_outcome,  # type: ignore
                    expected=test.expected,
                    observed="; ".join(observed_msgs),
                    step_results=step_results,
                    evidence_ids=test_evidence,
                    duration_ms=total_duration,
                    retry_count=total_retries,
                    error_code=error_code,
                )
            )

        await browser.close()

    return {
        "test_results": new_results,
        "evidence_manifest": evidence_manifest,
    }
