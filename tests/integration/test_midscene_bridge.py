import pytest

from app.core.state_manager import RunStateManager
from app.executors.midscene_executor import MidsceneWorkerClient
from app.executors.ui_engine import MidsceneWorkerEngine
from app.models import UIStep


@pytest.mark.integration
@pytest.mark.asyncio
async def test_midscene_worker_client_lifecycle():
    """Verify that Python can spawn the Node browser-worker, create a session, and cleanly tear it down."""
    client = MidsceneWorkerClient(
        run_id="test_bridge_001",
        headless=True,
        allowed_hosts=["127.0.0.1", "localhost"],
    )

    try:
        await client.start()
        assert client.session_id is not None
        assert client.port is not None
        assert client.port > 0

        # Execute navigate to worker health endpoint
        step = UIStep(
            action="navigate",
            params={"url": f"http://127.0.0.1:{client.port}/health"},
        )
        res = await client.execute_step(
            step=step,
            test_id="BRG-001",
            step_index=0,
        )
        assert res.outcome == "PASSED"
        assert res.engine in ("midscene", "playwright-node")
        assert res.duration_ms > 0
    finally:
        await client.close_session()
        client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_midscene_worker_engine_adapter():
    """Verify that the MidsceneWorkerEngine abstraction executes UISteps cleanly."""
    engine = MidsceneWorkerEngine(
        run_id="test_adapter_001",
        headless=True,
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    state_mgr = RunStateManager(run_id="test_adapter_001")

    try:
        await engine.start()
        step = UIStep(
            action="navigate",
            params={"url": f"http://127.0.0.1:{engine._client.port}/health"},
        )
        res = await engine.execute_step(
            step=step,
            test_id="BRG-002",
            step_index=0,
            state_manager=state_mgr,
        )
        assert res.outcome == "PASSED"
    finally:
        await engine.stop()
