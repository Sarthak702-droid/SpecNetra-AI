import time
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from app.config import settings
from app.core.recovery import RecoverableError
from app.core.security import assert_allowed_url
from app.core.state_manager import RunStateManager
from app.executors.assertions import assert_text, assert_url
from app.models import StepResult, UIStep


class LocatorResolutionError(Exception):
    pass


async def resolve_locator(page: Page, params: dict[str, Any]):
    """
    FR-006 Locator Priority:
    1. Accessible role and accessible name.
    2. Associated form labels.
    3. Stable data-testid attributes.
    4. Configured CSS selectors.
    """
    if params.get("role"):
        name = params.get("name")
        return page.get_by_role(params["role"], name=name)
    if params.get("label"):
        return page.get_by_label(params["label"])
    if params.get("testid"):
        return page.get_by_test_id(params["testid"])
    if params.get("css"):
        return page.locator(params["css"])
    raise LocatorResolutionError(f"No valid locator attributes in params: {params}")


async def capture_screenshot(page: Page, output_dir: Path, test_id: str) -> str:
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    file_path = screenshots_dir / f"{test_id}.png"
    try:
        await page.screenshot(path=str(file_path), full_page=True)
        return f"screenshots/{test_id}.png"
    except Exception:
        return ""


async def execute_ui_step(
    step: UIStep,
    page: Page,
    state_manager: RunStateManager,
    output_dir: Path,
    test_id: str,
    step_index: int = 0,
) -> StepResult:
    start_time = time.monotonic()
    timeout_ms = settings.test_timeout_ms

    try:
        if step.action == "navigate":
            target_url = step.params.get("url", "")
            # Replace placeholder variables like {appointment_id}
            if "{" in target_url and "}" in target_url:
                resources = await state_manager.get_all_resources()
                for k, v in resources.items():
                    target_url = target_url.replace(f"{{{k}}}", str(v))

            assert_allowed_url(target_url)
            try:
                await page.goto(target_url, timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception as e:
                if "timeout" in str(e).lower():
                    raise RecoverableError(
                        code="BROWSER_NAVIGATION_TIMEOUT", message=f"Navigation timeout: {e}"
                    )
                raise

        elif step.action == "fill_by_label":
            loc = await resolve_locator(page, step.params)
            value = step.params.get("value", "")
            await loc.fill(value, timeout=timeout_ms)

        elif step.action == "click_by_role":
            loc = await resolve_locator(page, step.params)
            await loc.click(timeout=timeout_ms)

        elif step.action == "assert_visible":
            loc = await resolve_locator(page, step.params)
            # Try waiting for visibility within timeout
            try:
                await loc.wait_for(state="visible", timeout=timeout_ms)
            except Exception:
                screenshot_rel = await capture_screenshot(page, output_dir, test_id)
                duration_ms = (time.monotonic() - start_time) * 1000.0
                evidence = [screenshot_rel] if screenshot_rel else []
                return StepResult(
                    step_index=step_index,
                    outcome="FAILED",
                    observed=f"Element was not visible: {step.params}",
                    duration_ms=duration_ms,
                    error_code="UI_ASSERTION_FAILED",
                    evidence_ids=evidence,
                )

        elif step.action == "assert_text":
            loc = await resolve_locator(page, step.params)
            expected = step.params.get("expected", "")
            # Replace placeholder variables like {appointment_id}
            if "{" in expected and "}" in expected:
                resources = await state_manager.get_all_resources()
                for k, v in resources.items():
                    expected = expected.replace(f"{{{k}}}", str(v))

            try:
                await loc.wait_for(state="visible", timeout=timeout_ms)
                actual_text = await loc.inner_text()
                res = assert_text(actual_text, expected)
                if not res.passed:
                    screenshot_rel = await capture_screenshot(page, output_dir, test_id)
                    evidence = [screenshot_rel] if screenshot_rel else []
                    return StepResult(
                        step_index=step_index,
                        outcome="FAILED",
                        observed=res.message,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                        error_code="UI_ASSERTION_FAILED",
                        evidence_ids=evidence,
                    )
            except Exception as e:
                screenshot_rel = await capture_screenshot(page, output_dir, test_id)
                evidence = [screenshot_rel] if screenshot_rel else []
                return StepResult(
                    step_index=step_index,
                    outcome="FAILED",
                    observed=f"Could not read text from element ({e})",
                    duration_ms=(time.monotonic() - start_time) * 1000.0,
                    error_code="UI_ASSERTION_FAILED",
                    evidence_ids=evidence,
                )

        elif step.action == "assert_url":
            expected = step.params.get("expected", "")
            actual_url = page.url
            res = assert_url(actual_url, expected)
            if not res.passed:
                screenshot_rel = await capture_screenshot(page, output_dir, test_id)
                evidence = [screenshot_rel] if screenshot_rel else []
                return StepResult(
                    step_index=step_index,
                    outcome="FAILED",
                    observed=res.message,
                    duration_ms=(time.monotonic() - start_time) * 1000.0,
                    error_code="UI_ASSERTION_FAILED",
                    evidence_ids=evidence,
                )

        elif step.action == "screenshot":
            screenshot_rel = await capture_screenshot(page, output_dir, test_id)
            duration_ms = (time.monotonic() - start_time) * 1000.0
            evidence = [screenshot_rel] if screenshot_rel else []
            return StepResult(
                step_index=step_index,
                outcome="PASSED",
                observed="Screenshot captured",
                duration_ms=duration_ms,
                evidence_ids=evidence,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        return StepResult(
            step_index=step_index,
            outcome="PASSED",
            observed=f"UI step {step.action} completed successfully",
            duration_ms=duration_ms,
        )

    except RecoverableError:
        raise
    except Exception as e:
        screenshot_rel = await capture_screenshot(page, output_dir, test_id)
        evidence = [screenshot_rel] if screenshot_rel else []
        duration_ms = (time.monotonic() - start_time) * 1000.0
        return StepResult(
            step_index=step_index,
            outcome="ERROR",
            observed=f"Browser execution exception: {e!s}",
            duration_ms=duration_ms,
            error_code="BROWSER_EXECUTION_ERROR",
            evidence_ids=evidence,
        )
