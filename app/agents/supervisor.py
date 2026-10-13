from pathlib import Path
from typing import Any

import httpx

from app.agents.planner import generate_test_plan
from app.config import settings
from app.core.input_loader import InputValidationError, load_inputs
from app.core.logging import get_logger
from app.core.recovery import RetryPolicy, SafetyError, with_retry
from app.core.state_manager import get_run_state_manager
from app.core.test_scheduler import SchedulerError, check_dependency_status, order_for_execution
from app.executors.api_executor import execute_api_step
from app.executors.ui_engine import create_ui_engine
from app.models import APIStep, RunState, StepResult, TestResult, UIStep

logger = get_logger(__name__)


async def validate_inputs_node(state: RunState) -> dict[str, Any]:
    req_paths = state.get("req_paths", {})
    req_path = Path(req_paths.get("requirements", "inputs/requirements.md"))
    openapi_path = Path(req_paths.get("openapi", "inputs/openapi.json"))
    scenarios_path = Path(req_paths.get("scenarios", "inputs/scenarios.json"))

    try:
        logger.info(f"Validating inputs from: {req_path}, {openapi_path}, {scenarios_path}")
        bundle = await load_inputs(req_path, openapi_path, scenarios_path)
        return {
            "input_bundle": bundle,
            "run_phase": "PLANNING",
        }
    except InputValidationError as e:
        logger.error(f"Input validation failed: {e}")
        return {
            "run_phase": "VALIDATION_FAILED",
            "errors": [str(e)],
        }
    except Exception as e:
        logger.error(f"Unexpected input error: {e}")
        return {
            "run_phase": "VALIDATION_FAILED",
            "errors": [f"Unexpected error loading inputs: {e}"],
        }


async def plan_tests_node(state: RunState) -> dict[str, Any]:
    bundle = state.get("input_bundle")
    if not bundle:
        return {
            "run_phase": "PLANNING_FAILED",
            "errors": ["Input bundle is missing"],
        }

    try:
        logger.info("Generating structured test plan")
        plan = await generate_test_plan(bundle)

        # Validate topological sort and enforce configured bounds
        order_for_execution(plan.tests, max_tests=settings.max_tests_per_run)

        return {
            "test_plan": plan,
            "run_phase": "EXECUTING",
        }
    except SchedulerError as e:
        logger.error(f"Test plan dependency scheduling error: {e}")
        return {
            "run_phase": "PLANNING_FAILED",
            "errors": [f"Scheduler error: {e}"],
        }
    except Exception as e:
        logger.error(f"Test planning failed: {e}")
        return {
            "run_phase": "PLANNING_FAILED",
            "errors": [f"Planning failed: {e}"],
        }


async def execute_tests_node(state: RunState) -> dict[str, Any]:
    """
    Unified dependency-aware test supervisor execution loop:
    1. Executes tests in topological order respecting dependencies.
    2. Marks dependent tests as BLOCKED if prerequisite fails or errors.
    3. Executes mixed API and UI steps in causal sequence.
    4. Enforces safe retry policies (read-only UI steps idempotent, mutations non-idempotent).
    5. Preserves full chronological step timeline in TestResult.
    """
    plan = state.get("test_plan")
    if not plan:
        return {"errors": ["No test plan found for execution"], "run_phase": "EVALUATING"}

    ordered_tests = order_for_execution(plan.tests, max_tests=settings.max_tests_per_run)
    run_id = state["run_id"]
    state_manager = get_run_state_manager(run_id)

    test_results: list[TestResult] = []
    evidence_manifest: list[dict[str, Any]] = []
    outcomes: dict[str, str] = {}

    has_ui = any(
        any(isinstance(s, UIStep) or getattr(s, "kind", None) == "ui_action" for s in t.steps)
        for t in ordered_tests
    )

    ui_engine = None
    if has_ui:
        try:
            hosts = (
                list(settings.allowed_target_hosts)
                if isinstance(settings.allowed_target_hosts, list)
                else [settings.allowed_target_hosts]
            )
            ui_engine = create_ui_engine(
                engine_name=settings.ui_engine,
                run_id=run_id,
                headless=settings.browser_headless,
                allowed_hosts=hosts,
            )
            await ui_engine.start()
        except Exception as e:
            logger.error(f"Failed to launch UI engine: {e}")
            return {
                "errors": [f"Browser initialization failed: {e}"],
                "run_phase": "EVALUATING",
            }

    async with httpx.AsyncClient() as http_client:
        try:
            for test in ordered_tests:
                # 1. Dependency check
                is_blocked, block_reason = check_dependency_status(test, outcomes)
                if is_blocked:
                    outcomes[test.test_id] = "BLOCKED"
                    test_results.append(
                        TestResult(
                            test_id=test.test_id,
                            requirement_ids=test.requirement_ids,
                            outcome="BLOCKED",
                            expected=test.expected,
                            observed=f"Dependency blocked: {block_reason}",
                            step_results=[],
                            duration_ms=0.0,
                            error_code="DEPENDENCY_BLOCKED",
                        )
                    )
                    continue

                # 2. Sequential step execution
                step_results: list[StepResult] = []
                test_outcome = "PASSED"
                total_duration = 0.0
                error_code = None
                observed_msgs = []
                total_retries = 0
                test_evidence: list[str] = []

                for idx, step in enumerate(test.steps):
                    is_api = (
                        isinstance(step, APIStep) or getattr(step, "kind", None) == "api_request"
                    )
                    is_ui = isinstance(step, UIStep) or getattr(step, "kind", None) == "ui_action"

                    if is_api:
                        policy = RetryPolicy(
                            max_retries=test.max_retries,
                            is_idempotent=(step.method in ("GET", "PUT", "DELETE", "HEAD")),
                        )
                        try:
                            step_res, retries = await with_retry(
                                execute_api_step,
                                policy,
                                step,
                                http_client,
                                state_manager,
                                step_index=idx,
                            )
                            total_retries += retries
                        except SafetyError as se:
                            step_res = StepResult(
                                step_index=idx,
                                outcome="FAILED",
                                observed=f"Safety violation: {se}",
                                duration_ms=0.0,
                                error_code="SAFETY_VIOLATION",
                            )
                        except Exception as e:
                            step_res = StepResult(
                                step_index=idx,
                                outcome="ERROR",
                                observed=f"API step failed after retries: {e}",
                                duration_ms=0.0,
                                error_code="STEP_EXECUTION_ERROR",
                            )

                    elif is_ui and ui_engine is not None:
                        # Safe UI retry policy: only read-only actions are idempotent
                        ui_is_idempotent = step.action in (
                            "navigate",
                            "assert_visible",
                            "assert_text",
                            "assert_url",
                            "screenshot",
                            "ai_assert",
                        )
                        policy = RetryPolicy(
                            max_retries=test.max_retries,
                            is_idempotent=ui_is_idempotent,
                        )
                        try:
                            step_res, retries = await with_retry(
                                ui_engine.execute_step,
                                policy,
                                step,
                                test.test_id,
                                idx,
                                state_manager,
                            )
                            total_retries += retries
                        except SafetyError as se:
                            step_res = StepResult(
                                step_index=idx,
                                outcome="FAILED",
                                observed=f"Safety violation: {se}",
                                duration_ms=0.0,
                                error_code="SAFETY_VIOLATION",
                            )
                        except Exception as e:
                            step_res = StepResult(
                                step_index=idx,
                                outcome="ERROR",
                                observed=f"UI step exception: {e}",
                                duration_ms=0.0,
                                error_code="STEP_EXECUTION_ERROR",
                            )
                    else:
                        step_res = StepResult(
                            step_index=idx,
                            outcome="ERROR",
                            observed=f"Unsupported step kind: {type(step)}",
                            duration_ms=0.0,
                            error_code="UNSUPPORTED_STEP",
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

                outcomes[test.test_id] = test_outcome
                test_results.append(
                    TestResult(
                        test_id=test.test_id,
                        requirement_ids=test.requirement_ids,
                        outcome=test_outcome,  # type: ignore
                        expected=test.expected,
                        observed="; ".join(observed_msgs) if observed_msgs else "No output",
                        step_results=step_results,
                        evidence_ids=test_evidence,
                        duration_ms=total_duration,
                        retry_count=total_retries,
                        error_code=error_code,
                    )
                )
        finally:
            if ui_engine:
                try:
                    await ui_engine.stop()
                except Exception as e:
                    logger.warning(f"Error closing UI engine: {e}")

    return {
        "test_results": test_results,
        "evidence_manifest": evidence_manifest,
        "run_phase": "EVALUATING",
    }
