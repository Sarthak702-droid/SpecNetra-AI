import json
import re
from pathlib import Path
from typing import Any

from openapi_spec_validator import validate as validate_openapi_spec

from app.models import InputBundle, Requirement, Scenario


class InputValidationError(Exception):
    """Raised when input files fail validation."""


def parse_requirements(text: str) -> list[Requirement]:
    requirements: list[Requirement] = []
    # Match headers like "## REQ-001 — User Authentication" or "## REQ-001: User Authentication"
    section_pattern = re.compile(r"^##\s+(REQ-\d+)[\s:—–-]+([^\n]+)", re.MULTILINE)
    matches = list(section_pattern.finditer(text))

    if not matches:
        raise InputValidationError(
            "No valid requirements found matching format '## REQ-XXX — Title'"
        )

    seen_ids = set()
    for i, match in enumerate(matches):
        req_id = match.group(1).strip()
        title = match.group(2).strip()

        if req_id in seen_ids:
            raise InputValidationError(f"Duplicate requirement ID detected: {req_id}")
        seen_ids.add(req_id)

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        # Parse priority: "Priority: P0"
        prio_match = re.search(r"Priority:\s*(P[0-2])", body, re.IGNORECASE)
        priority = prio_match.group(1).upper() if prio_match else "P0"

        requirements.append(
            Requirement(
                req_id=req_id,
                title=title,
                priority=priority,  # type: ignore
                description=body,
            )
        )

    return requirements


def extract_operation_ids(openapi_doc: dict[str, Any]) -> set[str]:
    op_ids = set()
    for path_item in openapi_doc.get("paths", {}).values():
        if isinstance(path_item, dict):
            for method, operation in path_item.items():
                if isinstance(operation, dict) and "operationId" in operation:
                    op_ids.add(operation["operationId"])
    return op_ids


async def load_inputs(
    req_path: Path,
    openapi_path: Path,
    scenarios_path: Path,
) -> InputBundle:
    # 1. Existence check
    for path, name in [
        (req_path, "requirements.md"),
        (openapi_path, "openapi.json"),
        (scenarios_path, "scenarios.json"),
    ]:
        if not path.exists():
            raise InputValidationError(f"Missing mandatory input file: {name} (looked at {path})")

    # 2. Parse requirements.md
    try:
        req_content = req_path.read_text(encoding="utf-8")
        requirements = parse_requirements(req_content)
    except Exception as e:
        if isinstance(e, InputValidationError):
            raise
        raise InputValidationError(f"Failed to parse requirements file: {e}")

    # 3. Parse and validate openapi.json
    try:
        openapi_doc = json.loads(openapi_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputValidationError(f"openapi.json has invalid JSON syntax: {e}")

    try:
        validate_openapi_spec(openapi_doc)
    except Exception as e:
        raise InputValidationError(f"OpenAPI validation error: {e}")

    valid_op_ids = extract_operation_ids(openapi_doc)

    # 4. Parse scenarios.json
    try:
        scenarios_data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputValidationError(f"scenarios.json has invalid JSON syntax: {e}")

    if not isinstance(scenarios_data, dict) or "scenarios" not in scenarios_data:
        raise InputValidationError("scenarios.json must contain a top-level 'scenarios' list")

    known_req_ids = {r.req_id for r in requirements}
    scenarios: list[Scenario] = []
    seen_scenario_ids = set()

    for sc_raw in scenarios_data["scenarios"]:
        sc = Scenario(**sc_raw)
        if sc.id in seen_scenario_ids:
            raise InputValidationError(f"Duplicate scenario ID: {sc.id}")
        seen_scenario_ids.add(sc.id)

        # Cross-reference requirement IDs
        for rid in sc.requirement_ids:
            if rid not in known_req_ids:
                raise InputValidationError(
                    f"Scenario '{sc.id}' references unknown requirement ID '{rid}'"
                )

        # Cross-reference operation IDs if API
        for op in sc.operations:
            if op.kind == "api" and op.operation_id:
                if op.operation_id not in valid_op_ids:
                    raise InputValidationError(
                        f"Scenario '{sc.id}' references unknown operationId '{op.operation_id}' in OpenAPI"
                    )

        scenarios.append(sc)

    return InputBundle(
        requirements=requirements,
        scenarios=scenarios,
        openapi_doc=openapi_doc,
    )
