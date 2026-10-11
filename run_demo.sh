#!/usr/bin/env bash
set -Eeuo pipefail

# SpecNetra AI - Interactive Testing Runner

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${VIRTUAL_ENV:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"

echo "[setup] Checking Python environment..."
if [ -z "${VIRTUAL_ENV:-}" ] && [ ! -x "$PYTHON_BIN" ]; then
    python3 -m venv "$VENV_DIR"
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    PYTHON_BIN="$VENV_DIR/bin/python"
else
    PYTHON_BIN="$(command -v python)"
fi

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "[setup] pip is missing; bootstrapping it..."
    "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null
fi

if ! "$PYTHON_BIN" -c "import pydantic, uvicorn, httpx, playwright" >/dev/null 2>&1; then
    echo "[setup] Installing SpecNetra dependencies..."
    "$PYTHON_BIN" -m pip install --upgrade pip
    "$PYTHON_BIN" -m pip install -e ".[dev]"
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import asyncio

from playwright.async_api import async_playwright


async def check_chromium() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        await browser.close()


asyncio.run(check_chromium())
PY
then
    echo "[setup] Installing the Playwright Chromium browser..."
    "$PYTHON_BIN" -m playwright install chromium
fi

MODE="${1:-healthy}"
HEADLESS="${2:-false}"

echo "=========================================="
echo " SpecNetra AI — Interactive Demo Runner"
echo "=========================================="

if [ "$MODE" == "--bug" ] || [ "$MODE" == "bug" ]; then
    echo "Mode: [DEFECTIVE / BUG DETECTION]"
    export DEMO_BUG_MODE="hide_created_appointment"
else
    echo "Mode: [HEALTHY TARGET]"
    export DEMO_BUG_MODE=""
fi

if [ "$HEADLESS" == "--headless" ]; then
    export BROWSER_HEADLESS="true"
    echo "Browser: Headless (Background)"
else
    export BROWSER_HEADLESS="false"
    echo "Browser: Headed (Visible on screen)"
fi

echo ""
echo "[1/3] Starting target Demo API (port 8001) & Web Frontend (port 3000)..."

"$PYTHON_BIN" -c "
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

trap "kill $SERVER_PID 2>/dev/null || true" EXIT

sleep 2

echo "[2/3] Launching SpecNetra AI Autonomous Testing Pipeline..."
echo ""

set +e
"$PYTHON_BIN" -m app.main \
  --requirements inputs/requirements.md \
  --openapi inputs/openapi.json \
  --scenarios inputs/scenarios.json \
  --api-url http://127.0.0.1:8001 \
  --web-url http://127.0.0.1:3000
EXIT_CODE=$?
set -e

echo ""
echo "[3/3] Execution finished (Exit Code: $EXIT_CODE)."
echo "Generated Artifacts:"
echo "  - Report:      output/report.md"
echo "  - JSON Log:    output/execution_log.json"
if [ -f output/screenshots/SMK-003.png ]; then
    echo "  - Screenshot:  output/screenshots/SMK-003.png"
fi
echo "=========================================="
exit $EXIT_CODE
