# SpecNetra AI — Architectural Design Document (DESIGN.md)

**Product Name:** SpecNetra AI  
**Tagline:** From Requirements to Reliable Tests  
**Version:** 1.0 (MVP)  
**Architecture:** Python Modular Monolith  

---

## 1. Executive Summary & Core Decisions

SpecNetra AI transforms software requirements (`requirements.md`), API specifications (`openapi.json`), and user scenarios (`scenarios.json`) into deterministic, executable tests without requiring manual script authoring.

### Fundamental Architectural Principle
> **AI plans and analyzes tests; deterministic execution engines determine test results.**

1. **Python Modular Monolith over Microservices:** Agents communicate through typed LangGraph state updates rather than network calls. This eliminates inter-service latency, token overhead, and distributed failure modes.
2. **Deterministic Execution:** Real requests are dispatched via **HTTPX** (API) and browser workflows via **Playwright** (Chromium). PASS/FAIL verdicts are strictly computed by deterministic assertion rules. LLMs are never permitted to guess or self-heal failed business assertions into PASS.
3. **Bounded Resilience:** Recovers only from narrowly defined transient errors (network timeouts, rate limits, UI rendering race conditions) with exponential backoff and safe semantic locator fallbacks.
4. **Cross-Layer State Sharing:** Resource identifiers generated at runtime (such as `appointment_id`) are safely transferred from backend API creation to browser verification within an isolated per-run namespace.

---

## 2. Multi-Agent Architecture & LangGraph State Machine

SpecNetra coordinates four specialized logical agents through LangGraph:

```
                  INPUT FILES
             (requirements.md, openapi.json, scenarios.json)
                      |
                      v
                INPUT VALIDATOR
                      |
                      v
              PLANNER / SUPERVISOR
                      |
                      v
               STRUCTURED TEST PLAN
                      |
                      v
                TEST SCHEDULER (Topological Sort)
                      |
             +--------+--------+
             |                 |
             v                 v
        API SPECIALIST    UI SPECIALIST
          (HTTPX)          (Playwright)
             |                 |
             +--------+--------+
                      |
                      v
               SHARED RUN STATE
           (appointment_id, tokens)
                      |
                      v
              EVALUATOR / RCA
                      |
                      v
                 FINAL REPORT
         (report.md, execution_log.json, screenshots)
```

### State Transitions

```
CREATED -> VALIDATING -> PLANNING -> EXECUTING -> EVALUATING -> COMPLETED
               |              |            |
               v              v            v
       VALIDATION_FAILED PLANNING_FAILED EXECUTION_ERROR
```

- A completed test run where defects are detected remains `COMPLETED` in lifecycle, while the `overall_outcome` is recorded as `FAILED`.

---

## 3. Agent Roles and Boundaries

### Agent A: Supervisor & Planner (`app/agents/supervisor.py`, `app/agents/planner.py`)
- **Inputs:** Validated `InputBundle` (requirements, OpenAPI, scenarios).
- **Processing:** Analyzes observable behaviors, maps scenarios to requirement IDs, and constructs a Pydantic-validated `TestPlan`.
- **Modes:** Autonomous AI planning via Pydantic AI (`output_type=TestPlan`) with automatic fallback to deterministic fixture planning for repeatable offline verification.
- **Constraints:** Never invents unverified behaviors or generates executable shell/Python commands.

### Agent B: API Specialist (`app/agents/api_specialist.py`, `app/executors/api_executor.py`)
- **Inputs:** `APIStep` specifications, headers, schemas, assertions.
- **Processing:** Async HTTP execution via `httpx.AsyncClient`. Asserts HTTP status codes, validates JSON responses against OpenAPI response schemas via `jsonschema`, and extracts generated identifiers (e.g. `appointment_id`).
- **Constraints:** Calls only allowlisted target hosts; non-idempotent operations are never retried blindly.

### Agent C: UI Specialist (`app/agents/ui_specialist.py`, `app/executors/browser_executor.py`)
- **Inputs:** `UIStep` browser actions, target URLs, expected selectors and text.
- **Processing:** Controls headless Chromium via Playwright. Resolves elements via semantic locator priorities (Accessible Role > Form Label > TestID > CSS). Takes full-page screenshots on assertion failures.
- **Constraints:** Separate assertions from selectors; never mutates expectations.

### Agent D: Evaluator & RCA (`app/agents/evaluator.py`, `app/reports/rca.py`)
- **Inputs:** Actual test outcomes, durations, error codes, screenshots, and requirement maps.
- **Processing:** Synthesizes observed failure evidence into Root Cause Analysis (RCA) hypotheses with confidence ratings and recommended debugging steps.
- **Constraints:** Distinguishes verified observations from hypotheses; never alters pass/fail verdicts.

---

## 4. Shared Run State & Cross-Layer Contracts

Shared state is maintained in `app/core/state_manager.py` using `RunStateManager`:

```python
class RunState(TypedDict):
    run_id: str
    run_phase: str
    input_bundle: InputBundle | None
    test_plan: TestPlan | None
    resource_refs: ResourceRefs
    auth_state: AuthState
    test_results: Annotated[list[TestResult], operator.add]
    evidence_manifest: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    evaluation: dict | None
```

### Cross-Layer State Contract (Scenario SC-002 -> SC-003)
1. **API Specialist** executes `POST /api/appointments`.
2. Backend returns HTTP 201 with `{"id": "apt_5021", "status": "confirmed"}`.
3. `api_executor` stores `apt_5021` under key `appointment_id` in `RunStateManager`.
4. **UI Specialist** reads `appointment_id` and substitutes dynamic URL `/appointments/{appointment_id}` -> `/appointments/apt_5021`.
5. Playwright verifies the specific appointment detail page.

---

## 5. Security Architecture

1. **Host & Scheme Allowlist:** `app/core/security.py` strictly restricts outgoing network connections to configured target hosts (`demo-api`, `demo-web`, `localhost`). Non-HTTP schemes (such as `file://`) are blocked immediately.
2. **Secret Redaction:** Raw tokens, passwords, and Authorization headers are masked as `[REDACTED]` in all execution logs and reports.
3. **Prompt Injection Defense:** Input documents and web responses are treated as untrusted data; prompt sanitization strips sensitive authentication keys before LLM invocation.

---

## 6. Recovery Policy & Safe Fallbacks

Per FR-008:
- **Eligible transient errors:** Connection timeouts (`CONN_TIMEOUT`), rate limits (`HTTP_429`), temporary 503, browser rendering timeouts (`BROWSER_NAVIGATION_TIMEOUT`).
- **Bounded retries:** Maximum 2 retries with exponential backoff (`wait = base * 2^attempt`).
- **Idempotency Guard:** Non-idempotent operations (such as HTTP `POST` without an idempotency key) immediately raise `SafetyError` upon failure rather than retrying.
- **Locator Hierarchy:** Role/Name -> Label -> Data-testid -> CSS. Alternate locators are tried only for the identical semantic element.
- **Immutable Failures:** A business assertion mismatch is recorded as `FAILED` and never self-healed.

---

## 7. Reporting & Output Structure

Every run outputs:
```
output/
├── execution_log.json    # Machine-readable structured execution logs
├── report.md             # 11-section comprehensive Markdown report
├── test_plan.json        # Machine-readable validated test plan
└── screenshots/          # Evidence screenshots for UI failures
    └── SMK-003.png
```
