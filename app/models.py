import operator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

# ── Input Models ──────────────────────────────────────────────────────────────


class Requirement(BaseModel):
    req_id: str  # e.g. "REQ-001"
    title: str
    priority: Literal["P0", "P1", "P2"] = "P0"
    description: str


class ScenarioOperation(BaseModel):
    kind: Literal["api", "ui"]
    operation_id: str | None = None
    action: str | None = None
    expect_failure: bool = False
    invalid_body: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    id: str
    name: str
    requirement_ids: list[str] = Field(min_length=1)
    priority: Literal["P0", "P1", "P2"] = "P0"
    dependencies: list[str] = Field(default_factory=list)
    operations: list[ScenarioOperation] = Field(default_factory=list)


class InputBundle(BaseModel):
    requirements: list[Requirement]
    scenarios: list[Scenario]
    openapi_doc: dict[str, Any]


# ── Test Plan Models ───────────────────────────────────────────────────────────


class APIStep(BaseModel):
    kind: Literal["api_request"] = "api_request"
    operation_id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    extract: dict[str, str] = Field(default_factory=dict)  # field_path -> resource_ref_key
    expect_failure: bool = False


class UIStep(BaseModel):
    kind: Literal["ui_action"] = "ui_action"
    action: Literal[
        "navigate",
        "fill_by_label",
        "click_by_role",
        "assert_visible",
        "assert_text",
        "assert_url",
        "screenshot",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    __test__ = False

    test_id: str
    requirement_ids: list[str] = Field(min_length=1)
    priority: Literal["P0", "P1", "P2"] = "P0"
    category: Literal["api", "ui", "cross_layer"]
    dependencies: list[str] = Field(default_factory=list)
    steps: list[APIStep | UIStep] = Field(default_factory=list)
    expected: str
    timeout_ms: int = 15000
    max_retries: int = 2


class TestPlan(BaseModel):
    __test__ = False

    plan_id: str
    tests: list[TestCase] = Field(min_length=1, max_length=20)


# ── Execution Result Models ────────────────────────────────────────────────────


class StepResult(BaseModel):
    step_index: int
    outcome: Literal["PASSED", "FAILED", "ERROR", "SKIPPED"]
    observed: str
    duration_ms: float
    retry_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None


class TestResult(BaseModel):
    test_id: str
    requirement_ids: list[str]
    outcome: Literal["PASSED", "FAILED", "ERROR", "BLOCKED", "SKIPPED"]
    expected: str
    observed: str
    step_results: list[StepResult] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    retry_count: int = 0
    duration_ms: float = 0.0
    error_code: str | None = None


# ── Shared Run State ───────────────────────────────────────────────────────────


class ResourceRefs(BaseModel):
    appointment_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AuthState(BaseModel):
    session_ref: str | None = None
    token_store_key: str | None = None


class RCAFinding(BaseModel):
    test_id: str
    requirement_ids: list[str]
    observed_evidence: str
    hypothesis: str
    confidence: Literal["high", "medium", "low"]
    next_debug_step: str


class RunState(TypedDict):
    run_id: str
    run_phase: (
        str  # CREATED | VALIDATING | PLANNING | EXECUTING | EVALUATING | COMPLETED | FAILED_TO_RUN
    )
    input_bundle: InputBundle | None
    test_plan: TestPlan | None
    resource_refs: ResourceRefs
    auth_state: AuthState
    test_results: Annotated[list[TestResult], operator.add]
    evidence_manifest: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    evaluation: dict[str, Any] | None
    req_paths: dict[str, str]
    started_at: str | None
    finished_at: str | None
