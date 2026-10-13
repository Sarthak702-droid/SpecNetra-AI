import "dotenv/config";
import { chromium } from "playwright";
import { PlaywrightAgent } from "@midscene/web/playwright";

async function main() {
  const url = process.env.TEST_WEB_URL || "https://automationintesting.online";
  const apiKey = process.env.MIDSCENE_MODEL_API_KEY || process.env.OPENAI_API_KEY;

  console.log("==================================================");
  console.log(" Midscene.js Browser Worker Standalone Smoke Test ");
  console.log("==================================================");
  console.log(`Target URL: ${url}`);
  console.log(`Vision Model: ${process.env.MIDSCENE_MODEL_NAME || "default"}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  const agent = new PlaywrightAgent(page);

  try {
    console.log(`[1/3] Navigating to ${url}...`);
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
    console.log("[PASS] Navigation successful");

    if (apiKey && apiKey !== "test-key") {
      console.log("[2/3] Executing positive Midscene aiAssert...");
      await agent.aiAssert("The page contains visible content or branding");
      console.log("[PASS] Positive AI assertion succeeded!");
    } else {
      console.log("[2/3] Skipping aiAssert (MIDSCENE_MODEL_API_KEY not configured)");
      console.log("      (To test live AI assertions, set MIDSCENE_MODEL_API_KEY in browser-worker/.env)");
    }

    console.log("[3/3] Teardown and cleanup...");
  } finally {
    await agent.destroy?.();
    await browser.close();
  }

  console.log("==================================================");
  console.log(" Smoke test finished successfully!               ");
  console.log("==================================================");
}

main().catch((err) => {
  console.error("[FAIL] Smoke test error:", err);
  process.exit(1);
});
