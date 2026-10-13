from pathlib import Path

import pytest

from app.agents.planner import build_fixture_plan, validate_test_plan
from app.config import settings
from app.core.input_loader import load_inputs


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_live_app_planning():
    """Verify that the public live application input bundle plans and validates cleanly."""
    bundle = await load_inputs(
        req_path=Path("inputs/public_live_app/requirements.md"),
        openapi_path=Path("inputs/public_live_app/openapi.json"),
        scenarios_path=Path("inputs/public_live_app/scenarios.json"),
    )

    orig_web = settings.web_base_url
    orig_api = settings.api_base_url
    try:
        settings.web_base_url = "https://automationintesting.online"
        settings.api_base_url = "https://restful-booker.herokuapp.com"

        plan = build_fixture_plan(bundle)
        assert len(plan.tests) == 5

        test_ids = [t.test_id for t in plan.tests]
        assert "SMK-001" in test_ids
        assert "SMK-002" in test_ids
        assert "SMK-003" in test_ids
        assert "REG-004" in test_ids
        assert "REG-005" in test_ids

        # Semantic validation must find 0 errors
        errs = validate_test_plan(plan, bundle)
        assert errs == []
    finally:
        settings.web_base_url = orig_web
        settings.api_base_url = orig_api


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clinify_bundle_planning():
    """Verify that the Clinify staging input bundle plans and validates cleanly."""
    bundle = await load_inputs(
        req_path=Path("inputs/clinify/requirements.md"),
        openapi_path=Path("inputs/clinify/openapi.json"),
        scenarios_path=Path("inputs/clinify/scenarios.json"),
    )

    plan = build_fixture_plan(bundle)
    assert len(plan.tests) == 5

    # Check that requirement coverage maps accurately
    planned_reqs = {r for t in plan.tests for r in t.requirement_ids}
    assert "REQ-CLN-001" in planned_reqs
    assert "REQ-CLN-002" in planned_reqs
    assert "REQ-CLN-003" in planned_reqs

    errs = validate_test_plan(plan, bundle)
    assert errs == []
