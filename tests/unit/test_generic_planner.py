import pytest

from app.agents.planner import (
    PlanningFailedError,
    build_fixture_plan,
    derive_sample_body_from_schema,
    extract_openapi_operations,
)
from app.models import (
    APIStep,
    InputBundle,
    Requirement,
    Scenario,
    ScenarioOperation,
    TestCase,
)


@pytest.fixture
def generic_openapi_doc():
    return {
        "openapi": "3.1.0",
        "info": {"title": "Warehouse Inventory API", "version": "1.0.0"},
        "paths": {
            "/api/items": {
                "post": {
                    "operationId": "createItem",
                    "summary": "Create an inventory item",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "sku": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                        "active": {"type": "boolean"},
                                    },
                                    "required": ["sku", "quantity"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "sku": {"type": "string"},
                                        },
                                        "required": ["id", "sku"],
                                    }
                                }
                            },
                        },
                        "422": {"description": "Unprocessable Entity"},
                    },
                },
                "get": {
                    "operationId": "listItems",
                    "summary": "List items",
                    "responses": {"200": {"description": "OK"}},
                },
            }
        },
    }


@pytest.mark.unit
def test_extract_openapi_operations(generic_openapi_doc):
    ops = extract_openapi_operations(generic_openapi_doc)
    assert "createItem" in ops
    assert ops["createItem"]["method"] == "POST"
    assert ops["createItem"]["path"] == "/api/items"
    assert "listItems" in ops
    assert ops["listItems"]["method"] == "GET"


@pytest.mark.unit
def test_derive_sample_body_from_schema():
    schema = {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "quantity": {"type": "integer"},
            "active": {"type": "boolean"},
        },
    }
    body = derive_sample_body_from_schema(schema)
    assert body["sku"] == "test_sku"
    assert body["quantity"] == 1
    assert body["active"] is True


@pytest.mark.unit
def test_generic_app_fixture_planning(generic_openapi_doc):
    bundle = InputBundle(
        requirements=[
            Requirement(
                req_id="REQ-INV-1", title="Item Creation", description="Create items", priority="P0"
            ),
            Requirement(
                req_id="REQ-INV-2", title="List Items", description="List inventory", priority="P1"
            ),
        ],
        scenarios=[
            Scenario(
                id="SC-001",
                name="Create inventory item",
                requirement_ids=["REQ-INV-1"],
                priority="P0",
                operations=[ScenarioOperation(kind="api", operation_id="createItem")],
            ),
            Scenario(
                id="SC-002",
                name="List items",
                requirement_ids=["REQ-INV-2"],
                priority="P1",
                dependencies=["SC-001"],
                operations=[ScenarioOperation(kind="api", operation_id="listItems")],
            ),
        ],
        openapi_doc=generic_openapi_doc,
    )

    plan = build_fixture_plan(bundle)
    assert len(plan.tests) == 2
    t1 = plan.tests[0]
    assert t1.test_id == "SMK-001"
    assert len(t1.steps) == 1
    api_step = t1.steps[0]
    assert isinstance(api_step, APIStep)
    assert api_step.operation_id == "createItem"
    assert api_step.method == "POST"
    assert api_step.path == "/api/items"
    assert any(a.get("expected") == 201 for a in api_step.assertions)


@pytest.mark.unit
def test_reject_empty_test_steps(generic_openapi_doc):
    _ = InputBundle(
        requirements=[Requirement(req_id="REQ-1", title="T", description="D", priority="P0")],
        scenarios=[],
        openapi_doc=generic_openapi_doc,
    )
    # A test with 0 steps must fail validation
    with pytest.raises(Exception):
        TestCase(
            test_id="T0",
            requirement_ids=["REQ-1"],
            priority="P0",
            category="api",
            steps=[],
            expected="Empty",
        )


@pytest.mark.unit
def test_reject_unsupported_ui_action(generic_openapi_doc):
    bundle = InputBundle(
        requirements=[Requirement(req_id="REQ-1", title="T", description="D", priority="P0")],
        scenarios=[
            Scenario(
                id="SC-001",
                name="Unknown UI action",
                requirement_ids=["REQ-1"],
                operations=[ScenarioOperation(kind="ui", action="non_existent_magic_action")],
            )
        ],
        openapi_doc=generic_openapi_doc,
    )
    with pytest.raises(PlanningFailedError):
        build_fixture_plan(bundle)
