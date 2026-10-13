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
async def test_midscene_healthy_e2e_run():
    """Verify that the full SpecNetra pipeline executes cleanly using UI_ENGINE=midscene."""
    reset_database()
    os.environ["DEMO_BUG_MODE"] = ""
    settings.demo_bug_mode = ""
    settings.api_base_url = "http://127.0.0.1:8001"
    settings.web_base_url = "http://127.0.0.1:3000"

    orig_engine = settings.ui_engine
    settings.ui_engine = "midscene"

    root_dir = Path(__file__).parent.parent.parent
    output_dir = root_dir / "output"

    try:
        async with run_demo_servers():
            initial_state: RunState = {
                "run_id": "run_midscene_healthy_001",
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
                "started_at": "2026-10-13T12:00:00Z",
                "finished_at": None,
            }

            final_state = await graph.ainvoke(initial_state)

            # 1. State completed
            assert final_state["run_phase"] == "COMPLETED"

            # 2. Check test outcomes
            results = final_state["test_results"]
            assert len(results) == 5

            for r in results:
                assert r.outcome == "PASSED", f"Test {r.test_id} failed: {r.observed}"
                assert len(r.requirement_ids) >= 1

            # 3. Check artifacts
            exec_log = output_dir / "execution_log.json"
            report_md = output_dir / "report.md"

            assert exec_log.exists()
            assert report_md.exists()

            log_data = json.loads(exec_log.read_text())
            assert log_data["overall_outcome"] == "PASSED"
            assert len(log_data["tests"]) == 5

            report_content = report_md.read_text()
            assert "UI Engine:** `midscene`" in report_content
    finally:
        settings.ui_engine = orig_engine
