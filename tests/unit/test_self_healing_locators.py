import pytest
from playwright.async_api import async_playwright

from app.core.state_manager import RunStateManager
from app.executors.browser_executor import execute_ui_step
from app.models import UIStep


@pytest.mark.unit
@pytest.mark.asyncio
async def test_self_healing_locator_fallback(tmp_path):
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <!-- Note: testid 'old-login-btn' has been changed to 'new-login-btn' in DOM -->
        <button id="submit-btn" data-testid="new-login-btn" role="button">Log In</button>
    </body>
    </html>
    """
    state_manager = RunStateManager(run_id="test_healing_run")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        # Primary locator has the obsolete testid 'old-login-btn', but candidate_locators
        # includes the accessible role or id or new-login-btn
        step = UIStep(
            action="click_by_role",
            params={"testid": "old-login-btn"},  # Obsolete primary locator
            candidate_locators=[
                {"testid": "new-login-btn"},  # Fallback 1
                {"role": "button", "name": "Log In"},  # Fallback 2
            ],
        )

        res = await execute_ui_step(step, page, state_manager, tmp_path, "TEST-HEAL-1")
        assert res.outcome == "PASSED"
        assert res.recovered_by is not None
        assert "Recovered" in res.recovered_by
        assert "new-login-btn" in res.recovered_by

        await browser.close()
