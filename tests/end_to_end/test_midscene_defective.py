import json
import os
from pathlib import Path

import pytest

from app.config import settings
from app.graph import graph
from app.models import AuthState, ResourceRefs, RunState
from demo.api.database import reset_database

from .server_helper import run_demo_servers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_midscene_defective_e2e_run():
    """Verify that injected UI defects are reliably detected when using UI_ENGINE=midscene."""
    reset_database()
    os.environ["DEMO_BUG_MODE"] = "hide_created_appointment"
    settings.demo_bug_mode = "hide_created_appointment"
    settings.api_base_url = "http://127.0.0.1:8001"
    settings.web_base_url = "http://127.0.0.1:3000"

    orig_engine = settings.ui_engine
    settings.ui_engine = "midscene"

    root_dir = Path(__file__).parent.parent.parent
    output_dir = root_dir / "output"

    try:
        async with run_demo_servers():
            initial_state: RunState = {
                "run_id": "run_midscene_defective_001",
                "run_phase": "VALIDATING",
                "input_bundle": None,
                "test_plan": None,
                "resource_refs": ResourceRefs(),
                "auth_state": AuthState(),
                "test_results": [],
                "evidence_manifest": [],
                "errors": [],
                "evaluation": None,
                "req_paths": {
                    "requirements": str(root_dir / "inputs" / "requirements.md"),
                    "openapi": str(root_dir / "inputs" / "openapi.json"),
                    "scenarios": str(root_dir / "inputs" / "scenarios.json"),
                },
                "started_at": "2026-10-13T12:05:00Z",
                "finished_at": None,
            }

            final_state = await graph.ainvoke(initial_state)

            # 1. Pipeline completed with evaluation
            assert final_state["run_phase"] == "COMPLETED"

            # 2. Results check
            results = {r.test_id: r for r in final_state["test_results"]}
            assert len(results) == 5

            # SMK-001 (auth) and SMK-002 (create appt) should pass
            assert results["SMK-001"].outcome == "PASSED"
            assert results["SMK-002"].outcome == "PASSED"

            # SMK-003 (view appointment) must fail because of injected defect
            assert results["SMK-003"].outcome in ("FAILED", "ERROR")
            assert results["SMK-003"].error_code in (
                "TEXT_ASSERTION_FAILED",
                "UI_ASSERTION_FAILED",
                "UI_TIMEOUT",
                "STEP_EXECUTION_ERROR",
            )

            # 3. Check artifacts and failure screenshot
            exec_log = output_dir / "execution_log.json"
            report_md = output_dir / "report.md"

            assert exec_log.exists()
            assert report_md.exists()

            log_data = json.loads(exec_log.read_text())
            assert log_data["overall_outcome"] == "FAILED"

            report_content = report_md.read_text()
            assert "Overall Outcome:** **FAILED**" in report_content
    finally:
        settings.ui_engine = orig_engine
