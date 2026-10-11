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
async def test_defective_e2e_run():
    reset_database()
    os.environ["DEMO_BUG_MODE"] = "hide_created_appointment"
    settings.demo_bug_mode = "hide_created_appointment"
    settings.api_base_url = "http://127.0.0.1:8001"
    settings.web_base_url = "http://127.0.0.1:3000"

    root_dir = Path(__file__).parent.parent.parent
    output_dir = root_dir / "output"

    async with run_demo_servers():
        initial_state: RunState = {
            "run_id": "run_defective_001",
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
            "started_at": "2026-10-11T12:05:00Z",
            "finished_at": None,
        }

        final_state = await graph.ainvoke(initial_state)

        # 1. State completed
        assert final_state["run_phase"] == "COMPLETED"

        results = {r.test_id: r for r in final_state["test_results"]}
        assert len(results) == 5

        # 2. SMK-001 (Login) must PASS
        assert results["SMK-001"].outcome == "PASSED"

        # 3. SMK-002 (API appointment creation) must PASS (returns 201 + ID)
        assert results["SMK-002"].outcome == "PASSED"

        # 4. SMK-003 (UI verification of created appointment) must FAIL!
        assert results["SMK-003"].outcome == "FAILED"
        assert results["SMK-003"].error_code == "UI_ASSERTION_FAILED"

        # 5. Screenshot captured for SMK-003
        assert len(results["SMK-003"].evidence_ids) >= 1
        screenshot_path = output_dir / results["SMK-003"].evidence_ids[0]
        assert screenshot_path.exists()

        # 6. Overall outcome is FAILED
        exec_log = output_dir / "execution_log.json"
        log_data = json.loads(exec_log.read_text())
        assert log_data["overall_outcome"] == "FAILED"

        # 7. RCA hypotheses exist and cite the failure
        evaluation = final_state["evaluation"]
        assert evaluation is not None
        assert evaluation["overall_verdict"] == "FAILED"
        findings = evaluation["findings"]
        assert len(findings) >= 1
        assert any(f["test_id"] == "SMK-003" for f in findings)
