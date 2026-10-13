from pathlib import Path

import pytest

from app.agents.planner import generate_test_plan
from app.core.input_loader import load_inputs
from app.core.test_scheduler import order_for_execution


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unrelated_target_planning():
    inv_dir = Path(__file__).parent.parent.parent / "inputs" / "demo_inventory"
    bundle = await load_inputs(
        inv_dir / "requirements.md",
        inv_dir / "openapi.json",
        inv_dir / "scenarios.json",
    )

    plan = await generate_test_plan(bundle)
    assert len(plan.tests) == 4

    ordered = order_for_execution(plan.tests)
    assert len(ordered) == 4

    # Verify SC-001 (createItem) runs before SC-002 (getItem)
    test_ids = [t.test_id for t in ordered]
    assert test_ids.index("SMK-001") < test_ids.index("SMK-002")

    # Verify operation details
    t1 = next(t for t in plan.tests if t.test_id == "SMK-001")
    assert t1.steps[0].operation_id == "createItem"
    assert t1.steps[0].path == "/api/items"
    assert any(a.get("expected") == 201 for a in t1.steps[0].assertions)

    t4 = next(t for t in plan.tests if t.test_id == "REG-004")
    assert t4.steps[0].expect_failure is True
    assert any(a.get("expected") == 422 for a in t4.steps[0].assertions)
