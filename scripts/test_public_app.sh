#!/usr/bin/env bash
set -Eeuo pipefail

# SpecNetra AI - Public Live SaaS Platform Testing Script
# Tests real external targets: restful-booker API & automationintesting.online Web UI

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${VIRTUAL_ENV:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"

if [ -z "${VIRTUAL_ENV:-}" ] && [ -x "$PYTHON_BIN" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
fi

echo "=========================================================="
echo " SpecNetra AI — Testing Real Public SaaS Web Application"
echo "=========================================================="
echo " Target API:  https://restful-booker.herokuapp.com"
echo " Target Web:  https://automationintesting.online"
echo " Scenarios:   3 Smoke Tests + 2 Negative Tests"
echo "=========================================================="
echo ""

python -m app.main \
  --requirements inputs/public_live_app/requirements.md \
  --openapi inputs/public_live_app/openapi.json \
  --scenarios inputs/public_live_app/scenarios.json \
  --api-url https://restful-booker.herokuapp.com \
  --web-url https://automationintesting.online

EXIT_CODE=$?
echo ""
echo "Execution finished with exit code: $EXIT_CODE"
echo "Check reports at:"
echo "  - Executive Report: output/report.md"
echo "  - Execution Logs:   output/execution_log.json"
exit $EXIT_CODE
