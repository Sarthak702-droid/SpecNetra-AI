import httpx
import pytest

from app.core.state_manager import RunStateManager
from app.executors.api_executor import execute_api_step
from app.models import APIStep
from demo.api.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_executor_against_demo_app():
    transport = httpx.ASGITransport(app=app)
    state_manager = RunStateManager(run_id="int_run_1")

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8001") as client:
        # 1. Login step
        login_step = APIStep(
            operation_id="loginUser",
            method="POST",
            path="/api/auth/login",
            body={"email": "tester@example.test", "password": "SecretPassword123!"},
            assertions=[
                {"kind": "assert_status", "expected": 200},
                {"kind": "assert_field", "path": "token_type", "expected": "bearer"},
            ],
            extract={"access_token": "session_token"},
        )
        res = await execute_api_step(login_step, client, state_manager)
        assert res.outcome == "PASSED"
        token = await state_manager.get_token("session_token")
        assert token is not None

        # 2. Create appointment step
        create_step = APIStep(
            operation_id="createAppointment",
            method="POST",
            path="/api/appointments",
            body={
                "patient_name": "Integration Patient",
                "starts_at": "2026-11-01T10:00:00+05:30",
                "reason": "General Checkup",
            },
            assertions=[
                {"kind": "assert_status", "expected": 201},
                {"kind": "assert_field", "path": "status", "expected": "confirmed"},
            ],
            extract={"id": "appointment_id"},
        )
        res2 = await execute_api_step(create_step, client, state_manager)
        assert res2.outcome == "PASSED"
        apt_id = await state_manager.get_resource("appointment_id")
        assert apt_id is not None
        assert apt_id.startswith("apt_")

        # 3. Invalid login step
        invalid_login_step = APIStep(
            operation_id="loginUser",
            method="POST",
            path="/api/auth/login",
            body={"email": "tester@example.test", "password": "WrongPassword!"},
            assertions=[
                {"kind": "assert_status", "expected": 401},
                {"kind": "assert_field", "path": "error.code", "expected": "INVALID_CREDENTIALS"},
            ],
            expect_failure=True,
        )
        res3 = await execute_api_step(invalid_login_step, client, state_manager)
        assert res3.outcome == "PASSED"  # The assertions matched the expected 401
