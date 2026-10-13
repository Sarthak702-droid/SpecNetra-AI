import json
import os
from typing import Any

from app.config import settings
from app.core.contract_validation import extract_response_schema
from app.core.logging import get_logger
from app.core.security import assert_allowed_url
from app.models import (
    APIStep,
    InputBundle,
    TestCase,
    TestPlan,
    UIStep,
)

logger = get_logger(__name__)

ALLOWED_UI_ACTIONS = {
    "navigate",
    "fill_by_label",
    "click_by_role",
    "assert_visible",
    "assert_text",
    "assert_url",
    "screenshot",
    "ai_act",
    "ai_assert",
    "ai_wait_for",
    "ai_query",
}


class PlanningFailedError(Exception):
    pass


def extract_openapi_operations(openapi_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extracts all operation definitions mapped by operationId from an OpenAPI specification."""
    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in openapi_doc.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "head"):
            if method in path_item and isinstance(path_item[method], dict):
                op_data = path_item[method]
                op_id = op_data.get("operationId")
                if op_id:
                    operations[op_id] = {
                        "method": method.upper(),
                        "path": path,
                        "summary": op_data.get("summary", ""),
                        "parameters": op_data.get("parameters", []),
                        "requestBody": op_data.get("requestBody", {}),
                        "responses": op_data.get("responses", {}),
                    }
    return operations


def derive_sample_body_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Generates dummy valid values matching an OpenAPI object schema properties."""
    sample: dict[str, Any] = {}
    props = schema.get("properties", {})
    for prop_name, prop_spec in props.items():
        prop_type = prop_spec.get("type", "string")
        if prop_type == "string":
            sample[prop_name] = f"test_{prop_name}"
        elif prop_type == "integer":
            sample[prop_name] = 1
        elif prop_type == "number":
            sample[prop_name] = 1.0
        elif prop_type == "boolean":
            sample[prop_name] = True
        elif prop_type == "array":
            sample[prop_name] = []
        elif prop_type == "object":
            sample[prop_name] = {}
    return sample


def validate_test_plan(plan: TestPlan, bundle: InputBundle) -> list[str]:
    """
    Semantic validator ensuring:
    1. Every test has at least 1 step and at least 1 verifiable assertion.
    2. Requirement IDs are traceable.
    3. Operation IDs exist in OpenAPI.
    4. UI actions are supported and URLs are allowed.
    """
    errors: list[str] = []
    req_ids = {r.req_id for r in bundle.requirements}
    openapi_ops = extract_openapi_operations(bundle.openapi_doc)
    openapi_paths = set(bundle.openapi_doc.get("paths", {}).keys())

    if not plan.tests:
        errors.append("Test plan has no test cases")
        return errors

    for test in plan.tests:
        if not test.steps:
            errors.append(f"Test '{test.test_id}' has 0 steps (empty test cases are rejected)")
            continue

        for r_id in test.requirement_ids:
            if r_id not in req_ids:
                errors.append(f"Test '{test.test_id}' references unknown requirement '{r_id}'")

        has_assertion = False
        for step_idx, step in enumerate(test.steps):
            is_api = isinstance(step, APIStep) or getattr(step, "kind", None) == "api_request"
            is_ui = isinstance(step, UIStep) or getattr(step, "kind", None) == "ui_action"

            if is_api:
                if step.assertions:
                    has_assertion = True
                if step.operation_id not in openapi_ops:
                    clean_path = step.path.split("?")[0]
                    if clean_path not in openapi_paths and not any(
                        p in step.path for p in openapi_paths
                    ):
                        errors.append(
                            f"Test '{test.test_id}' step {step_idx}: operation_id '{step.operation_id}' not found in OpenAPI"
                        )
            elif is_ui:
                if step.action not in ALLOWED_UI_ACTIONS:
                    errors.append(
                        f"Test '{test.test_id}' step {step_idx}: unsupported UI action '{step.action}'"
                    )
                if step.action in ("assert_visible", "assert_text", "assert_url", "ai_assert"):
                    has_assertion = True
                if step.action == "navigate":
                    raw_url = step.params.get("url", "")
                    try:
                        clean_url = raw_url.split("{")[0].rstrip("/") if "{" in raw_url else raw_url
                        if clean_url:
                            assert_allowed_url(clean_url)
                    except Exception as e:
                        errors.append(f"Test '{test.test_id}' step {step_idx}: disallowed URL: {e}")

        if not has_assertion:
            errors.append(
                f"Test '{test.test_id}' has no executable assertions or checks (under-asserted tests rejected)"
            )

    return errors


def build_generic_api_step(
    op_id: str,
    op_spec: dict[str, Any],
    expect_failure: bool = False,
    invalid_body: bool = False,
    details: dict[str, Any] | None = None,
    openapi_doc: dict[str, Any] | None = None,
) -> APIStep:
    """Builds a deterministic APIStep directly from an OpenAPI operation contract or scenario details."""
    details = details or {}
    method = details.get("method") or op_spec["method"]
    path = details.get("path") or op_spec["path"]
    headers = details.get("headers", {})

    # Body derivation
    body = details.get("body")
    if invalid_body and body is None:
        body = {"invalid_field": None}
    elif body is None and method in ("POST", "PUT", "PATCH"):
        req_content = op_spec.get("requestBody", {}).get("content", {})
        json_schema = req_content.get("application/json", {}).get("schema", {})
        if json_schema:
            body = derive_sample_body_from_schema(json_schema)
        else:
            body = {}

    # Assertions derivation
    if details.get("assertions"):
        assertions = details["assertions"]
    elif invalid_body:
        assertions = [{"kind": "assert_status", "expected": details.get("expect_status", 422)}]
    elif expect_failure:
        assertions = [{"kind": "assert_status", "expected": details.get("expect_status", 401)}]
    else:
        responses = op_spec.get("responses", {})
        success_status = details.get("expect_status", 200)
        if "expect_status" not in details:
            for code in (200, 201, 204):
                if str(code) in responses:
                    success_status = code
                    break
        assertions = [{"kind": "assert_status", "expected": success_status}]
        if openapi_doc:
            schema = extract_response_schema(openapi_doc, op_id, success_status)
            if schema:
                assertions.append({"kind": "assert_json_schema", "schema": schema})

    extract = details.get("extract", {})
    return APIStep(
        operation_id=op_id,
        method=method,  # type: ignore
        path=path,
        body=body,
        headers=headers,
        assertions=assertions,
        extract=extract,
        expect_failure=expect_failure or invalid_body,
    )


def build_fixture_plan(bundle: InputBundle) -> TestPlan:
    """
    Deterministic fixture-based planner mode.
    Maps scenarios and requirements into executable TestCases directly,
    supporting both demo appointment specifics and arbitrary OpenAPI operations.
    """
    tests: list[TestCase] = []
    openapi_ops = extract_openapi_operations(bundle.openapi_doc)

    is_demo_clinic = "Appointment API" in bundle.openapi_doc.get("info", {}).get("title", "")

    for sc in bundle.scenarios:
        steps: list[APIStep | UIStep] = []
        is_api = any(op.kind == "api" for op in sc.operations)
        is_ui = any(op.kind == "ui" for op in sc.operations)
        category = "cross_layer" if (is_api and is_ui) else ("api" if is_api else "ui")

        for op in sc.operations:
            if op.kind == "api":
                op_id = op.operation_id or ""
                # Check for recognized appointment demo operations ONLY if running the local demo clinic
                if is_demo_clinic and op_id == "loginUser" and not op.details:
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
                elif is_demo_clinic and op_id == "createAppointment" and not op.details:
                    if op.invalid_body:
                        steps.append(
                            APIStep(
                                operation_id="createAppointment",
                                method="POST",
                                path="/api/appointments",
                                body={"patient_name": ""},
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
                elif op_id in openapi_ops:
                    # Generic OpenAPI derived operation!
                    generic_step = build_generic_api_step(
                        op_id=op_id,
                        op_spec=openapi_ops[op_id],
                        expect_failure=op.expect_failure,
                        invalid_body=op.invalid_body,
                        details=op.details,
                        openapi_doc=bundle.openapi_doc,
                    )
                    steps.append(generic_step)
                else:
                    raise PlanningFailedError(
                        f"Unknown API operation '{op_id}' in scenario '{sc.id}' not found in OpenAPI"
                    )

            elif op.kind == "ui":
                action = op.action or ""
                if action in ALLOWED_UI_ACTIONS:
                    params = dict(op.details) if op.details else {}
                    if action == "navigate" and "url" in params:
                        raw_u = str(params["url"])
                        if raw_u.startswith("/"):
                            params["url"] = f"{settings.web_base_url.rstrip('/')}{raw_u}"
                        elif "{web_base_url}" in raw_u:
                            params["url"] = raw_u.replace(
                                "{web_base_url}", settings.web_base_url.rstrip("/")
                            )
                    steps.append(UIStep(action=action, params=params))  # type: ignore
                elif is_demo_clinic and action == "verify_dashboard_visible":
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
                elif is_demo_clinic and action == "verify_appointment_visible":
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
                else:
                    raise PlanningFailedError(
                        f"Unsupported UI action '{action}' in scenario '{sc.id}'"
                    )

        if not steps:
            raise PlanningFailedError(
                f"Scenario '{sc.id}' generated 0 executable steps (empty tests are disallowed)"
            )

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

    plan = TestPlan(plan_id="plan_fixture_001", tests=tests)
    validation_errs = validate_test_plan(plan, bundle)
    if validation_errs:
        raise PlanningFailedError("; ".join(validation_errs))
    return plan


async def generate_test_plan(bundle: InputBundle) -> TestPlan:
    """
    Generates a validated TestPlan using configured LLM via pydantic-ai
    or deterministic fixture mode.
    """
    if settings.plan_mode == "fixture":
        logger.info("Using deterministic fixture planning mode")
        return build_fixture_plan(bundle)

    # AI Mode with pydantic-ai
    try:
        # Ensure OpenAI API key is propagated to environment
        if settings.llm_api_key and settings.llm_api_key != "test-key":
            os.environ["OPENAI_API_KEY"] = settings.llm_api_key

        from pydantic_ai import Agent

        planner_agent = Agent(
            f"{settings.llm_provider}:{settings.llm_model}",
            output_type=TestPlan,
            system_prompt="""
You are an expert test planning agent for SpecNetra AI.
Generate a structured TestPlan Pydantic model for the given requirements, OpenAPI operations, and scenarios.
Rules:
1. Every test must reference valid requirement IDs.
2. Every test must have at least one executable check (assert_status, assert_field, assert_json_schema, assert_visible, assert_text, assert_url, or ai_assert).
3. Every test must contain at least 1 step. Zero-step tests are strictly prohibited.
4. Steps must be strictly limited to 'api_request' or 'ui_action'.
5. UI actions must only be one of: 'navigate', 'fill_by_label', 'click_by_role', 'assert_visible', 'assert_text', 'assert_url', 'screenshot', 'ai_act', 'ai_assert', 'ai_wait_for', 'ai_query'.
6. Do NOT hallucinate shell commands or external tools.
""",
        )

        prompt_data = {
            "requirements": [r.model_dump() for r in bundle.requirements],
            "scenarios": [s.model_dump() for s in bundle.scenarios],
            "openapi_operations": extract_openapi_operations(bundle.openapi_doc),
        }
        res = await planner_agent.run(json.dumps(prompt_data))
        plan = res.output

        # Perform strict semantic validation on the AI-generated plan
        val_errors = validate_test_plan(plan, bundle)
        if val_errors:
            raise PlanningFailedError(
                f"AI-generated plan failed semantic validation: {'; '.join(val_errors)}"
            )

        return plan
    except Exception as e:
        logger.warning(f"AI planning failed ({e}); checking fallback")
        if settings.plan_mode == "ai_strict":
            raise PlanningFailedError(f"AI planning failed under strict mode: {e}")
        return build_fixture_plan(bundle)
