import json
from typing import Any

from app.config import settings
from app.core.contract_validation import extract_response_schema
from app.core.logging import get_logger
from app.models import (
    APIStep,
    InputBundle,
    TestCase,
    TestPlan,
    UIStep,
)

logger = get_logger(__name__)


class PlanningFailedError(Exception):
    pass


def build_fixture_plan(bundle: InputBundle) -> TestPlan:
    """
    Deterministic fixture-based planner mode.
    Maps scenarios and requirements into executable TestCases directly.
    """
    tests: list[TestCase] = []

    # Map scenario ops to APIStep / UIStep
    for sc in bundle.scenarios:
        steps: list[APIStep | UIStep] = []
        is_api = any(op.kind == "api" for op in sc.operations)
        is_ui = any(op.kind == "ui" for op in sc.operations)

        category = "cross_layer" if (is_api and is_ui) else ("api" if is_api else "ui")

        for op in sc.operations:
            if op.kind == "api":
                if op.operation_id == "loginUser":
                    if op.expect_failure:
                        steps.append(
                            APIStep(
                                operation_id="loginUser",
                                method="POST",
                                path="/api/auth/login",
                                body={"email": "wrong@example.test", "password": "WrongPassword!"},
                                assertions=[
                                    {"kind": "assert_status", "expected": 401},
                                    {
                                        "kind": "assert_field",
                                        "path": "error.code",
                                        "expected": "INVALID_CREDENTIALS",
                                    },
                                ],
                                expect_failure=True,
                            )
                        )
                    else:
                        steps.append(
                            APIStep(
                                operation_id="loginUser",
                                method="POST",
                                path="/api/auth/login",
                                body={
                                    "email": settings.test_user_email,
                                    "password": settings.test_user_password,
                                },
                                assertions=[
                                    {"kind": "assert_status", "expected": 200},
                                    {
                                        "kind": "assert_field",
                                        "path": "token_type",
                                        "expected": "bearer",
                                    },
                                    {
                                        "kind": "assert_field",
                                        "path": "access_token",
                                        "expected": None,
                                    },
                                ],
                            )
                        )
                elif op.operation_id == "createAppointment":
                    if op.invalid_body:
                        steps.append(
                            APIStep(
                                operation_id="createAppointment",
                                method="POST",
                                path="/api/appointments",
                                body={"patient_name": ""},  # Missing starts_at and empty name
                                assertions=[
                                    {"kind": "assert_status", "expected": 422},
                                ],
                                expect_failure=True,
                            )
                        )
                    else:
                        schema = extract_response_schema(
                            bundle.openapi_doc, "createAppointment", 201
                        )
                        assertions: list[dict[str, Any]] = [
                            {"kind": "assert_status", "expected": 201},
                            {"kind": "assert_field", "path": "id", "expected": None},
                            {"kind": "assert_field", "path": "status", "expected": "confirmed"},
                        ]
                        if schema:
                            assertions.append({"kind": "assert_json_schema", "schema": schema})

                        steps.append(
                            APIStep(
                                operation_id="createAppointment",
                                method="POST",
                                path="/api/appointments",
                                body={
                                    "patient_name": "Demo Patient",
                                    "starts_at": "2026-11-01T10:00:00+05:30",
                                    "reason": "Routine checkup",
                                },
                                assertions=assertions,
                                extract={"id": "appointment_id"},
                            )
                        )

            elif op.kind == "ui":
                if op.action == "verify_dashboard_visible":
                    steps.extend(
                        [
                            UIStep(
                                action="navigate", params={"url": f"{settings.web_base_url}/login"}
                            ),
                            UIStep(
                                action="fill_by_label",
                                params={"label": "Email", "value": settings.test_user_email},
                            ),
                            UIStep(
                                action="fill_by_label",
                                params={"label": "Password", "value": settings.test_user_password},
                            ),
                            UIStep(
                                action="click_by_role", params={"role": "button", "name": "Sign in"}
                            ),
                            UIStep(action="assert_visible", params={"testid": "appointment-list"}),
                        ]
                    )
                elif op.action == "verify_appointment_visible":
                    steps.extend(
                        [
                            UIStep(
                                action="navigate",
                                params={
                                    "url": f"{settings.web_base_url}/appointments/{{appointment_id}}"
                                },
                            ),
                            UIStep(
                                action="assert_visible",
                                params={"testid": "appointment-detail"},
                            ),
                            UIStep(
                                action="assert_text",
                                params={"testid": "appointment-detail", "expected": "Demo Patient"},
                            ),
                        ]
                    )

        # Map scenario ID to test ID (e.g. SC-001 -> SMK-001 or REG-001)
        test_id = sc.id.replace("SC-00", "SMK-00" if sc.priority == "P0" else "REG-00")
        dep_tests = [
            d.replace("SC-00", "SMK-00" if "001" in d or "002" in d or "003" in d else "REG-00")
            for d in sc.dependencies
        ]

        tests.append(
            TestCase(
                test_id=test_id,
                requirement_ids=sc.requirement_ids,
                priority=sc.priority,
                category=category,  # type: ignore
                dependencies=dep_tests,
                steps=steps,
                expected=f"Execution of scenario '{sc.name}' matches requirements {sc.requirement_ids}",
            )
        )

    return TestPlan(plan_id="plan_fixture_001", tests=tests)


async def generate_test_plan(bundle: InputBundle) -> TestPlan:
    """
    Generates a validated TestPlan using either configured LLM via pydantic-ai
    or deterministic fixture mode.
    """
    if settings.plan_mode == "fixture":
        logger.info("Using deterministic fixture planning mode")
        return build_fixture_plan(bundle)

    # AI Mode with pydantic-ai
    try:
        from pydantic_ai import Agent

        planner_agent = Agent(
            f"{settings.llm_provider}:{settings.llm_model}",
            output_type=TestPlan,
            system_prompt="""
You are an expert test planning agent for SpecNetra AI.
Generate a structured TestPlan Pydantic model for the given requirements, OpenAPI operations, and scenarios.
Rules:
1. Every test must reference valid requirement IDs.
2. Every test must have verifiable expected results.
3. Steps must be strictly limited to 'api_request' or 'ui_action'.
4. Do NOT hallucinate shell commands or external tools.
""",
        )

        prompt_data = {
            "requirements": [r.model_dump() for r in bundle.requirements],
            "scenarios": [s.model_dump() for s in bundle.scenarios],
            "openapi_paths": list(bundle.openapi_doc.get("paths", {}).keys()),
        }
        res = await planner_agent.run(json.dumps(prompt_data))
        plan = res.output
        return plan
    except Exception as e:
        logger.warning(f"AI planning failed ({e}); falling back to verified fixture plan")
        return build_fixture_plan(bundle)
