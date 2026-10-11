from pathlib import Path
from typing import Any

from app.agents.planner import generate_test_plan
from app.core.input_loader import InputValidationError, load_inputs
from app.core.logging import get_logger
from app.core.test_scheduler import SchedulerError, order_for_execution
from app.models import RunState

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

        # Validate topological sort of dependencies
        order_for_execution(plan.tests)

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
