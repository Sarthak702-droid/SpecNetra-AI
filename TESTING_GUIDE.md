# SpecNetra AI — Testing & Verification Guide

> **Status:** Ready for execution.

## Goal Description

This guide outlines exactly how to test and observe **SpecNetra AI** in action, step-by-step:
1. **Headed Live Mode (Visible Browser):** Watch Playwright launch Chromium on your screen, fill in forms, and click buttons in real time.
2. **Healthy Mode vs Defective Bug Mode:** Verify both a 100% clean pass and an intentional bug catch with screenshot capture and AI Root Cause Analysis (RCA).
3. **Inspecting Artifacts:** View the generated Markdown report (`output/report.md`), structured JSON log (`output/execution_log.json`), and failure screenshot (`output/screenshots/SMK-003.png`).
4. **Docker Compose Mode:** Test the single-command containerized setup.

---

## Testing Methods Overview

| Method | What It Shows | How It Works |
|---|---|---|
| **Method 1: Headed UI Run (Recommended)** | Watch the browser test live on your screen | Runs target servers and CLI with `BROWSER_HEADLESS=false` |
| **Method 2: Defective Bug Run** | Shows real failure detection + RCA | Triggers `DEMO_BUG_MODE=hide_created_appointment`, fails SMK-003, captures screenshot |
| **Method 3: Full Pytest Suite** | Runs all 25 automated tests | Runs unit, integration, and E2E verification in seconds |
| **Method 4: Docker Compose** | Complete containerized pipeline | Builds all 3 containers (`demo-api`, `demo-web`, `runner`) and outputs reports |

---

## Step-by-Step Instructions

### Method 1 — Watch the Browser Test Live (Headed Mode)

To watch Chromium visibly open on your screen and execute the tests:

```bash
cd "/home/sarthaktripathy/Documents/SpecNetra AI"
source .venv/bin/activate

# 1. Start the Demo API and Web target in the background
python -c "
import asyncio, uvicorn
from demo.api.main import app as api_app
from tests.end_to_end.server_helper import web_app

async def main():
    api = uvicorn.Server(uvicorn.Config(api_app, host='127.0.0.1', port=8001, log_level='warning'))
    web = uvicorn.Server(uvicorn.Config(web_app, host='127.0.0.1', port=3000, log_level='warning'))
    await asyncio.gather(api.serve(), web.serve())

asyncio.run(main())
" &
SERVER_PID=$!

# 2. Run SpecNetra with visible browser (BROWSER_HEADLESS=false)
BROWSER_HEADLESS=false python -m app.main \
  --requirements inputs/requirements.md \
  --openapi inputs/openapi.json \
  --scenarios inputs/scenarios.json \
  --api-url http://127.0.0.1:8001 \
  --web-url http://127.0.0.1:3000

# 3. Stop background servers
kill $SERVER_PID
```

**What you will see:**
1. Console shows `[INFO] SpecNetra AI initialized` and `[PASS] Inputs valid`.
2. A Chromium window opens on your desktop.
3. It navigates to `http://127.0.0.1:3000/login`, automatically types `tester@example.test`, types the password, and clicks **Sign in**.
4. The API Specialist generates an appointment (`apt_5021`).
5. Chromium navigates to `http://127.0.0.1:3000/appointments/apt_5021` and verifies the patient details.
6. Console prints `Passed: 5`, `Failed: 0`.

---

### Method 2 — Test Intentional Bug Detection & RCA (Defective Mode)

To verify that the framework detects real bugs and never falsely marks broken functionality as PASSED:

```bash
cd "/home/sarthaktripathy/Documents/SpecNetra AI"
source .venv/bin/activate

# 1. Start demo servers with the bug switch enabled
DEMO_BUG_MODE=hide_created_appointment python -c "
import asyncio, uvicorn
from demo.api.main import app as api_app
from tests.end_to_end.server_helper import web_app

async def main():
    api = uvicorn.Server(uvicorn.Config(api_app, host='127.0.0.1', port=8001, log_level='warning'))
    web = uvicorn.Server(uvicorn.Config(web_app, host='127.0.0.1', port=3000, log_level='warning'))
    await asyncio.gather(api.serve(), web.serve())

asyncio.run(main())
" &
SERVER_PID=$!

# 2. Run SpecNetra test framework
DEMO_BUG_MODE=hide_created_appointment python -m app.main \
  --requirements inputs/requirements.md \
  --openapi inputs/openapi.json \
  --scenarios inputs/scenarios.json \
  --api-url http://127.0.0.1:8001 \
  --web-url http://127.0.0.1:3000

# 3. Stop background servers
kill $SERVER_PID
```

**What you will observe:**
1. `SMK-002` (API creation) **PASSES** (Backend created the appointment and returned HTTP 201).
2. `SMK-003` (UI view) **FAILS** with `UI_ASSERTION_FAILED` because the appointment is missing from the UI.
3. Playwright takes a full-page screenshot of the failure.
4. Console reports:
   ```text
   [FAILED] SMK-003: Element was not visible: {'testid': 'appointment-detail'}
   [INFO] Evaluating failures and Root Cause Analysis...
   [INFO] RCA status: FAILED
   Passed: 4
   Failed: 1
   ```
5. Exit code is `1` (indicating test suite failure).

---

### Method 3 — Inspecting Evidence & Reports

After running Method 1 or Method 2, inspect the generated artifacts:

1. **View the Markdown Report:**
   ```bash
   cat output/report.md
   ```
   Contains all 11 sections: Run ID, Application Info, Smoke & Regression results, Requirement Coverage Matrix (`REQ-001`, `REQ-002`, `REQ-003`), Failure Details, and Root Cause Analysis hypotheses with confidence ratings.

2. **View the Structured Execution Log:**
   ```bash
   cat output/execution_log.json
   ```
   Contains machine-readable results, durations in milliseconds, retry counts, and evidence links.

3. **View the Failure Screenshot:**
   ```bash
   xdg-open output/screenshots/SMK-003.png 2>/dev/null || file output/screenshots/SMK-003.png
   ```

---

### Method 4 — Test with Docker Compose (Single Command)

```bash
cd "/home/sarthaktripathy/Documents/SpecNetra AI"

# Healthy run
docker compose up --build --exit-code-from runner

# Defective run (Intentional Bug)
DEMO_BUG_MODE=hide_created_appointment docker compose up --build --exit-code-from runner
```

---

### Method 5 — Run Automated Pytest Suite

```bash
cd "/home/sarthaktripathy/Documents/SpecNetra AI"
source .venv/bin/activate

# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# End-to-end tests only
pytest tests/end_to_end/ -v

# All 25 tests
pytest tests/ -v
```
