from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import settings
from app.core.logging import get_logger
from app.core.state_manager import RunStateManager
from app.executors.browser_executor import execute_ui_step
from app.executors.midscene_executor import MidsceneWorkerClient
from app.models import StepResult, UIStep

logger = get_logger(__name__)


class UIEngine(ABC):
    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def execute_step(
        self,
        step: UIStep,
        test_id: str,
        step_index: int,
        state_manager: RunStateManager,
        test_context: dict[str, Any] | None = None,
    ) -> StepResult:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass


class PythonBrowserEngine(UIEngine):
    """Legacy Python Playwright UI execution engine."""

    def __init__(self, run_id: str, headless: bool = True):
        self.run_id = run_id
        self.headless = headless
        self._pw: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        self._page = await self._context.new_page()

    async def execute_step(
        self,
        step: UIStep,
        test_id: str,
        step_index: int,
        state_manager: RunStateManager,
        test_context: dict[str, Any] | None = None,
    ) -> StepResult:
        if not self._page:
            raise RuntimeError("PythonBrowserEngine is not started")

        return await execute_ui_step(
            step=step,
            page=self._page,
            state_manager=state_manager,
            output_dir=Path(settings.output_dir),
            test_id=test_id,
            step_index=step_index,
        )

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass


class MidsceneWorkerEngine(UIEngine):
    """Node.js / Midscene-based UI execution engine."""

    def __init__(
        self,
        run_id: str,
        headless: bool = True,
        allowed_hosts: list[str] | None = None,
    ):
        self.run_id = run_id
        self.headless = headless
        self.allowed_hosts = allowed_hosts or []
        self._client: MidsceneWorkerClient | None = None

    async def start(self) -> None:
        self._client = MidsceneWorkerClient(
            run_id=self.run_id,
            headless=self.headless,
            allowed_hosts=self.allowed_hosts,
        )
        await self._client.start()

    async def execute_step(
        self,
        step: UIStep,
        test_id: str,
        step_index: int,
        state_manager: RunStateManager,
        test_context: dict[str, Any] | None = None,
    ) -> StepResult:
        if not self._client:
            raise RuntimeError("MidsceneWorkerEngine is not started")

        # Resolve templated params like {appointment_id} or {web_base_url}
        resources = await state_manager.get_all_resources()
        params = dict(step.params)
        for k, v in list(params.items()):
            if isinstance(v, str):
                for r_k, r_v in resources.items():
                    v = v.replace(f"{{{r_k}}}", str(r_v))
                if "{web_base_url}" in v:
                    v = v.replace("{web_base_url}", settings.web_base_url.rstrip("/"))
                params[k] = v

        return await self._client.execute_step(
            step=step,
            test_id=test_id,
            step_index=step_index,
            params=params,
        )

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.close_session()
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


def create_ui_engine(
    engine_name: str | None = None,
    run_id: str = "run_default",
    headless: bool = True,
    allowed_hosts: list[str] | None = None,
) -> UIEngine:
    """Factory to instantiate the appropriate UI engine."""
    chosen = (engine_name or settings.ui_engine).lower()
    if chosen == "midscene":
        logger.info(f"Using MidsceneWorkerEngine for run {run_id}")
        return MidsceneWorkerEngine(
            run_id=run_id,
            headless=headless,
            allowed_hosts=allowed_hosts,
        )
    logger.info(f"Using legacy PythonBrowserEngine for run {run_id}")
    return PythonBrowserEngine(run_id=run_id, headless=headless)
