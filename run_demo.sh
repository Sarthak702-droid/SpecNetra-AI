#!/usr/bin/env bash
set -e

# SpecNetra AI - Interactive Testing Runner

MODE="${1:-healthy}"
HEADLESS="${2:-false}"

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

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

trap "kill $SERVER_PID 2>/dev/null || true" EXIT

sleep 2

echo "[2/3] Launching SpecNetra AI Autonomous Testing Pipeline..."
echo ""

set +e
python -m app.main \
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
