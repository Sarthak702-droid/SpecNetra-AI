import asyncio
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.models import StepResult, UIStep

logger = get_logger(__name__)


class MidsceneBridgeError(Exception):
    pass


class MidsceneWorkerClient:
    """Manages spawning the Node.js browser-worker and communicating over local HTTP protocol."""

    def __init__(self, run_id: str, headless: bool = True, allowed_hosts: list[str] | None = None):
        self.run_id = run_id
        self.headless = headless
        self.allowed_hosts = allowed_hosts or []
        self.worker_process: subprocess.Popen | None = None
        self.port: int | None = None
        self.auth_token: str = secrets.token_hex(16)
        self.session_id: str | None = None
        self.http_client: httpx.AsyncClient | None = None
        self._base_url: str | None = None

    async def start(self) -> None:
        """Starts worker process on an ephemeral port and creates a browser session."""
        worker_dir = Path(__file__).parent.parent.parent / "browser-worker"
        server_entry = worker_dir / "dist" / "server.js"
        if not server_entry.exists():
            server_entry = worker_dir / "src" / "server.ts"

        cmd = (
            ["node", str(server_entry)]
            if str(server_entry).endswith(".js")
            else ["npx", "tsx", str(server_entry)]
        )

        env = os.environ.copy()
        env["WORKER_PORT"] = "0"
        env["WORKER_AUTH_TOKEN"] = self.auth_token

        logger.info(f"Spawning browser-worker from {server_entry}...")
        self.worker_process = subprocess.Popen(
            cmd,
            cwd=str(worker_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Wait for [WORKER_READY] PORT=\d+
        loop = asyncio.get_running_loop()
        port_future = loop.create_future()

        def read_stdout():
            if not self.worker_process or not self.worker_process.stdout:
                return
            for line in self.worker_process.stdout:
                match = re.search(r"\[WORKER_READY\] PORT=(\d+)", line)
                if match:
                    p = int(match.group(1))
                    if not port_future.done():
                        loop.call_soon_threadsafe(port_future.set_result, p)
                    break

        await loop.run_in_executor(None, read_stdout)
        try:
            self.port = await asyncio.wait_for(port_future, timeout=10.0)
        except TimeoutError:
            self.close()
            raise MidsceneBridgeError("Timed out waiting for browser worker readiness")

        self._base_url = f"http://127.0.0.1:{self.port}"
        self.http_client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            timeout=float(settings.test_timeout_ms / 1000.0) + 10.0,
        )

        # Create session
        create_payload = {
            "run_id": self.run_id,
            "headless": self.headless,
            "allowed_hosts": self.allowed_hosts,
        }
        res = await self.http_client.post("/v1/session", json=create_payload)
        if res.status_code != 201:
            self.close()
            raise MidsceneBridgeError(
                f"Failed to create worker session (status {res.status_code}): {res.text}"
            )

        data = res.json()
        self.session_id = data["session_id"]
        logger.info(f"Worker session initialized: {self.session_id} on port {self.port}")

    async def execute_step(
        self,
        step: UIStep,
        test_id: str,
        step_index: int,
        params: dict[str, Any] | None = None,
    ) -> StepResult:
        if not self.http_client or not self.session_id:
            raise MidsceneBridgeError("Worker client is not started")

        command = {
            "protocol_version": "1.0",
            "run_id": self.run_id,
            "test_id": test_id,
            "step_index": step_index,
            "action": step.action,
            "params": params if params is not None else step.params,
            "candidate_locators": step.candidate_locators,
            "timeout_ms": settings.test_timeout_ms,
        }

        try:
            res = await self.http_client.post(
                f"/v1/session/{self.session_id}/step",
                json=command,
                timeout=float(settings.test_timeout_ms / 1000.0) + 15.0,
            )
        except Exception as e:
            return StepResult(
                step_index=step_index,
                outcome="ERROR",
                observed=f"Worker communication failure: {e}",
                duration_ms=0.0,
                error_code="WORKER_COMM_ERROR",
                engine="midscene",
            )

        if res.status_code != 200:
            return StepResult(
                step_index=step_index,
                outcome="ERROR",
                observed=f"Worker step returned HTTP {res.status_code}: {res.text}",
                duration_ms=0.0,
                error_code="WORKER_HTTP_ERROR",
                engine="midscene",
            )

        data = res.json()
        details = data.get("details", {})
        console_logs = details.get("console_errors", [])
        failed_requests = details.get("failed_requests", [])
        recovered_by = details.get("recovered_by")

        return StepResult(
            step_index=step_index,
            outcome=data.get("outcome", "ERROR"),
            observed=data.get("observed", ""),
            duration_ms=float(data.get("duration_ms", 0.0)),
            evidence_ids=data.get("evidence_ids", []),
            error_code=data.get("error_code"),
            recovered_by=recovered_by,
            console_logs=console_logs,
            network_errors=failed_requests,
            engine=data.get("engine", "midscene"),
            details=details,
        )

    async def close_session(self) -> None:
        if self.http_client and self.session_id:
            try:
                await self.http_client.delete(f"/v1/session/{self.session_id}")
            except Exception:
                pass
            self.session_id = None

    def close(self) -> None:
        if self.worker_process:
            try:
                self.worker_process.terminate()
                self.worker_process.wait(timeout=2.0)
            except Exception:
                try:
                    self.worker_process.kill()
                except Exception:
                    pass
            self.worker_process = None
