# SpecNetra AI

> **From Requirements to Reliable Tests**  
> Autonomous Multi-Agent Software Testing Framework

---

## 1. Overview

SpecNetra AI transforms application requirements (`requirements.md`), API definitions (`openapi.json`), and user scenarios (`scenarios.json`) into deterministic, executable tests without manual test script authoring.

It coordinates four specialized logical agents:
1. **Planner / Supervisor Agent** — Interprets specifications and constructs structured test plans.
2. **API Testing Agent** — Executes deterministic HTTP requests and validates response contracts with HTTPX.
3. **UI Testing Agent** — Automates browser workflows and validates element rendering with Playwright.
4. **Evaluator / RCA Agent** — Correlates cross-layer execution evidence and performs Root Cause Analysis.

---

## 2. Key Features

- **Cross-Layer State Sharing:** Dynamically passes backend resource IDs (e.g. `appointment_id`) from API creation directly to browser UI verification.
- **Strictly Grounded Pass/Fail:** Deterministic assertion rules determine test verdicts; the AI never invents results or self-heals broken business logic into PASS.
- **Bounded Error Recovery:** Handles network timeouts and rate limits with exponential backoff and safe semantic locator fallbacks.
- **Evidence-Backed RCA:** Captures screenshots upon UI assertion failures and generates root cause hypotheses.
- **Security-First Execution:** Enforces allowlisted target hosts, scheme filters, and sensitive token redaction.

---

## 3. Quick Start (Single Command with Docker Compose)

### Prerequisites
- Docker & Docker Compose

### 1. Configure Environment
```bash
cp .env.example .env
```

### 2. Run SpecNetra in Healthy Mode
```bash
docker compose up --build
```
This builds and starts:
- `demo-api`: FastAPI backend on port 8001
- `demo-web`: Vite/TypeScript frontend on port 3000
- `runner`: Executes the SpecNetra test pipeline and writes reports to `./output`

### 3. Run Intentional Bug Detection Demo
To test defect detection, activate the intentional defect switch:
```bash
DEMO_BUG_MODE=hide_created_appointment docker compose up --build
```
In this mode:
- `SMK-002` (API appointment creation) **PASSES** (HTTP 201 + ID returned).
- `SMK-003` (UI appointment verification) **FAILS** (element not found).
- A failure screenshot is saved to `output/screenshots/SMK-003.png`.
- The Evaluator generates an evidence-backed Root Cause Analysis (RCA) hypothesis in `output/report.md`.

---

## 4. Local Development

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

### Run Tests
```bash
# Run unit tests
pytest tests/unit/ -v

# Run integration tests
pytest tests/integration/ -v

# Run end-to-end tests
pytest tests/end_to_end/ -v

# Run full test suite
pytest tests/ -v
```

### Run SpecNetra CLI
```bash
python -m app.main \
  --requirements inputs/requirements.md \
  --openapi inputs/openapi.json \
  --scenarios inputs/scenarios.json
```

---

## 5. Artifacts & Reporting

Every completed execution produces:
```
output/
├── execution_log.json    # Machine-readable execution logs
├── report.md             # Detailed Markdown report
├── test_plan.json        # Structured test plan
└── screenshots/          # Evidence screenshots for UI failures
    └── SMK-003.png
```

---

## 6. Continuous Integration (CI)

A GitHub Actions workflow is provided in `.github/workflows/ci.yml` running:
1. **Lint:** Ruff formatting and style check.
2. **Unit Tests:** Fast unit tests (scheduler, security, assertions, recovery).
3. **Integration Tests:** API executor and Playwright browser tests.
4. **E2E Healthy Run:** Complete execution against healthy target.
5. **E2E Defective Run:** Intentional bug detection, screenshot capture, and artifact uploads.
