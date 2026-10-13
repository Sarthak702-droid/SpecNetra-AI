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


async def resolve_single_locator(page: Page, params: dict[str, Any]):
    """Resolves a single locator strategy from parameters."""
    if params.get("role"):
        name = params.get("name")
        return page.get_by_role(params["role"], name=name)
    if params.get("label"):
        return page.get_by_label(params["label"])
    if params.get("testid"):
        return page.get_by_test_id(params["testid"])
    if params.get("css"):
        return page.locator(params["css"])
    if params.get("text"):
        return page.get_by_text(params["text"])
    raise LocatorResolutionError(f"No valid locator attributes in params: {params}")


async def resolve_locator(page: Page, params: dict[str, Any]):
    return await resolve_single_locator(page, params)


async def resolve_locator_with_healing(
    page: Page,
    params: dict[str, Any],
    candidate_locators: list[dict[str, Any]] | None = None,
) -> tuple[Any, str | None]:
    """
    Self-healing locator resolver:
    1. Tries primary locator.
    2. If not immediately found, tries candidate_locators in order.
    3. Tries inferred attribute fallbacks (e.g. data-testid attribute, name selector).
    Returns (locator, recovered_by_reason).
    """
    candidates: list[dict[str, Any]] = [params]
    if candidate_locators:
        candidates.extend(candidate_locators)

    # Inferred fallbacks
    if params.get("testid"):
        t_id = params["testid"]
        if not any(c.get("css") == f"[data-testid='{t_id}']" for c in candidates):
            candidates.append({"css": f"[data-testid='{t_id}']"})
        if not any(c.get("css") == f"#{t_id}" for c in candidates):
            candidates.append({"css": f"#{t_id}"})
    if params.get("label"):
        lbl = params["label"].lower()
        if not any(c.get("css") == f"input[name='{lbl}']" for c in candidates):
            candidates.append({"css": f"input[name='{lbl}']"})
        if not any(c.get("css") == f"input[id='{lbl}']" for c in candidates):
            candidates.append({"css": f"input[id='{lbl}']"})

    for idx, cand in enumerate(candidates):
        try:
            loc = await resolve_single_locator(page, cand)
            count = await loc.count()
            if count > 0:
                recovered_by = None if idx == 0 else f"Recovered via candidate {idx}: {cand}"
                return loc, recovered_by
        except Exception:
            continue

    # Fall back to primary locator to allow standard wait_for / timeout exception handling
    return await resolve_single_locator(page, params), None


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
    recovered_by: str | None = None
    console_logs: list[str] = []
    network_errors: list[str] = []

    def on_console(msg: Any):
        if msg.type in ("error", "warning"):
            console_logs.append(f"[{msg.type}] {msg.text}")

    def on_req_failed(req: Any):
        network_errors.append(f"Failed request: {req.method} {req.url} ({req.failure})")

    page.on("console", on_console)
    page.on("requestfailed", on_req_failed)

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
            loc, rec = await resolve_locator_with_healing(
                page, step.params, getattr(step, "candidate_locators", None)
            )
            if rec:
                recovered_by = rec
            value = step.params.get("value", "")
            await loc.fill(value, timeout=timeout_ms)

        elif step.action == "click_by_role":
            loc, rec = await resolve_locator_with_healing(
                page, step.params, getattr(step, "candidate_locators", None)
            )
            if rec:
                recovered_by = rec
            await loc.click(timeout=timeout_ms)

        elif step.action == "assert_visible":
            loc, rec = await resolve_locator_with_healing(
                page, step.params, getattr(step, "candidate_locators", None)
            )
            if rec:
                recovered_by = rec
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
                    console_logs=list(console_logs),
                    network_errors=list(network_errors),
                )

        elif step.action == "assert_text":
            loc, rec = await resolve_locator_with_healing(
                page, step.params, getattr(step, "candidate_locators", None)
            )
            if rec:
                recovered_by = rec
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
                        console_logs=list(console_logs),
                        network_errors=list(network_errors),
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
                    console_logs=list(console_logs),
                    network_errors=list(network_errors),
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
                    console_logs=list(console_logs),
                    network_errors=list(network_errors),
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
                console_logs=list(console_logs),
                network_errors=list(network_errors),
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        observed_msg = f"UI step {step.action} completed successfully"
        if recovered_by:
            observed_msg += f" ({recovered_by})"
        return StepResult(
            step_index=step_index,
            outcome="PASSED",
            observed=observed_msg,
            duration_ms=duration_ms,
            recovered_by=recovered_by,
            console_logs=list(console_logs),
            network_errors=list(network_errors),
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
            console_logs=list(console_logs),
            network_errors=list(network_errors),
        )
