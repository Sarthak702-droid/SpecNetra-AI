from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.core.state_manager import RunStateManager
from app.executors.browser_executor import execute_ui_step
from app.models import UIStep


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browser_executor_with_fixture_html(tmp_path: Path):
    state_manager = RunStateManager(run_id="test_ui_run")
    await state_manager.store_resource("appointment_id", "apt_9999")

    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <label for="username">Username</label>
        <input id="username" type="text" />
        <button role="button">Submit</button>
        <div data-testid="appointment-detail">Patient apt_9999 confirmed</div>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        # 1. Fill input by label
        step_fill = UIStep(
            action="fill_by_label", params={"label": "Username", "value": "testuser"}
        )
        res1 = await execute_ui_step(step_fill, page, state_manager, tmp_path, "TEST-001")
        assert res1.outcome == "PASSED"

        # 2. Click button by role
        step_click = UIStep(action="click_by_role", params={"role": "button", "name": "Submit"})
        res2 = await execute_ui_step(step_click, page, state_manager, tmp_path, "TEST-001")
        assert res2.outcome == "PASSED"

        # 3. Assert element visible by testid
        step_vis = UIStep(action="assert_visible", params={"testid": "appointment-detail"})
        res3 = await execute_ui_step(step_vis, page, state_manager, tmp_path, "TEST-001")
        assert res3.outcome == "PASSED"

        # 4. Assert element missing -> triggers failure + screenshot
        step_missing = UIStep(action="assert_visible", params={"testid": "non-existent-box"})
        res4 = await execute_ui_step(step_missing, page, state_manager, tmp_path, "TEST-FAIL-001")
        assert res4.outcome == "FAILED"
        assert res4.error_code == "UI_ASSERTION_FAILED"
        assert len(res4.evidence_ids) >= 1
        screenshot_file = tmp_path / res4.evidence_ids[0]
        assert screenshot_file.exists()

        await browser.close()
