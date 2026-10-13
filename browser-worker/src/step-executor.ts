import { Page, Locator } from "playwright";
import { PlaywrightAgent } from "@midscene/web/playwright";
import { UiCommand, UiStepResult } from "./schemas.js";
import { assertAllowedUrl } from "./security.js";
import { EvidenceCollector } from "./evidence.js";

export class StepExecutionError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "StepExecutionError";
    this.code = code;
  }
}

export class StepExecutor {
  private agent: PlaywrightAgent | null = null;

  constructor(
    private page: Page,
    private evidenceCollector: EvidenceCollector,
    private allowedHosts: string[]
  ) {}

  private getAgent(): PlaywrightAgent {
    if (!this.agent) {
      this.agent = new PlaywrightAgent(this.page);
    }
    return this.agent;
  }

  async destroy(): Promise<void> {
    if (this.agent) {
      await this.agent.destroy?.();
      this.agent = null;
    }
  }

  private async resolveSingleLocator(params: Record<string, any>): Promise<Locator> {
    if (params.role) {
      return this.page.getByRole(params.role, { name: params.name });
    }
    if (params.label) {
      return this.page.getByLabel(params.label);
    }
    if (params.testid) {
      return this.page.getByTestId(params.testid);
    }
    if (params.css) {
      return this.page.locator(params.css);
    }
    if (params.selector) {
      return this.page.locator(params.selector);
    }
    if (params.xpath) {
      return this.page.locator(`xpath=${params.xpath}`);
    }
    if (params.text) {
      return this.page.getByText(params.text);
    }
    throw new StepExecutionError("LOCATOR_NOT_FOUND", `No valid locator attributes in params: ${JSON.stringify(params)}`);
  }

  private async resolveLocatorWithHealing(
    params: Record<string, any>,
    candidateLocators: Record<string, any>[] = []
  ): Promise<{ locator: Locator; recoveredBy?: string }> {
    const candidates: Record<string, any>[] = [params, ...candidateLocators];

    // Inferred fallbacks
    if (params.testid) {
      candidates.push({ css: `[data-testid='${params.testid}']` });
      candidates.push({ css: `#${params.testid}` });
    }

    for (let i = 0; i < candidates.length; i++) {
      const cand = candidates[i];
      try {
        const loc = await this.resolveSingleLocator(cand);
        // Fast probe: check if element is present within 1.5s
        await loc.first().waitFor({ state: "attached", timeout: i === 0 ? 3000 : 1500 });
        const recoveredBy = i > 0 ? `candidate_${i}:${JSON.stringify(cand)}` : undefined;
        return { locator: loc.first(), recoveredBy };
      } catch {
        continue;
      }
    }

    // Default to primary locator so normal error handling takes place
    const fallback = await this.resolveSingleLocator(params);
    return { locator: fallback.first() };
  }

  async execute(command: UiCommand): Promise<UiStepResult> {
    const startTime = Date.now();
    const { action, params, candidate_locators, timeout_ms, run_id, test_id, step_index } = command;
    const evidenceIds: string[] = [];
    let observed = "";
    let outcome: "PASSED" | "FAILED" | "ERROR" | "TIMED_OUT" = "PASSED";
    let errorCode: string | null = null;
    const details: Record<string, any> = {};

    try {
      switch (action) {
        case "navigate": {
          const url = params.url;
          if (!url) throw new StepExecutionError("INVALID_PARAMS", "Missing 'url' parameter for navigate");
          assertAllowedUrl(url, this.allowedHosts);
          await this.page.goto(url, { timeout: timeout_ms, waitUntil: "domcontentloaded" });
          observed = `Navigated to ${url}`;
          break;
        }

        case "fill_by_label": {
          const value = params.value ?? "";
          const { locator, recoveredBy } = await this.resolveLocatorWithHealing(params, candidate_locators);
          if (recoveredBy) details.recovered_by = recoveredBy;
          await locator.fill(String(value), { timeout: timeout_ms });
          observed = `Filled value into input: ${params.label ?? params.testid ?? "target"}`;
          break;
        }

        case "click_by_role": {
          const { locator, recoveredBy } = await this.resolveLocatorWithHealing(params, candidate_locators);
          if (recoveredBy) details.recovered_by = recoveredBy;
          await locator.click({ timeout: timeout_ms });
          observed = `Clicked element: ${params.role ?? params.name ?? "target"}`;
          break;
        }

        case "assert_visible": {
          const { locator, recoveredBy } = await this.resolveLocatorWithHealing(params, candidate_locators);
          if (recoveredBy) details.recovered_by = recoveredBy;
          await locator.waitFor({ state: "visible", timeout: timeout_ms });
          observed = `Element visible: ${JSON.stringify(params)}`;
          break;
        }

        case "assert_text": {
          const expected = String(params.expected ?? "");
          const { locator, recoveredBy } = await this.resolveLocatorWithHealing(params, candidate_locators);
          if (recoveredBy) details.recovered_by = recoveredBy;
          await locator.waitFor({ state: "visible", timeout: timeout_ms });
          const text = (await locator.innerText({ timeout: timeout_ms })) || "";
          if (!text.includes(expected)) {
            outcome = "FAILED";
            errorCode = "TEXT_ASSERTION_FAILED";
            observed = `Expected text '${expected}' not found in observed '${text}'`;
          } else {
            observed = `Text matched '${expected}'`;
          }
          break;
        }

        case "assert_url": {
          const expectedUrl = String(params.expected_url ?? params.url ?? "");
          const currentUrl = this.page.url();
          if (!currentUrl.includes(expectedUrl) && currentUrl !== expectedUrl) {
            outcome = "FAILED";
            errorCode = "URL_ASSERTION_FAILED";
            observed = `Current URL '${currentUrl}' does not match expected '${expectedUrl}'`;
          } else {
            observed = `URL matches '${expectedUrl}'`;
          }
          break;
        }

        case "screenshot": {
          const shot = await this.evidenceCollector.captureScreenshot(this.page, run_id, test_id, step_index);
          if (shot) evidenceIds.push(shot);
          observed = `Screenshot captured`;
          break;
        }

        case "ai_assert": {
          const prompt = params.prompt ?? params.assertion ?? params.text;
          if (!prompt) throw new StepExecutionError("INVALID_PARAMS", "Missing 'prompt' for ai_assert");
          const agent = this.getAgent();
          details.model = process.env.MIDSCENE_MODEL_NAME ?? "default-vision-model";
          details.assertion_type = "semantic-visual";
          await agent.aiAssert(prompt);
          observed = `Midscene AI assertion passed: "${prompt}"`;
          break;
        }

        case "ai_act": {
          const prompt = params.prompt ?? params.action ?? params.text;
          if (!prompt) throw new StepExecutionError("INVALID_PARAMS", "Missing 'prompt' for ai_act");
          const agent = this.getAgent();
          details.model = process.env.MIDSCENE_MODEL_NAME ?? "default-vision-model";
          await agent.aiAct(prompt);
          observed = `Midscene AI action executed: "${prompt}"`;
          break;
        }

        case "ai_wait_for": {
          const prompt = params.prompt ?? params.assertion ?? params.text;
          if (!prompt) throw new StepExecutionError("INVALID_PARAMS", "Missing 'prompt' for ai_wait_for");
          const agent = this.getAgent();
          await agent.aiWaitFor(prompt, { timeout: timeout_ms });
          observed = `Midscene AI waited successfully for: "${prompt}"`;
          break;
        }

        case "ai_query": {
          const prompt = params.prompt ?? params.query ?? params.text;
          if (!prompt) throw new StepExecutionError("INVALID_PARAMS", "Missing 'prompt' for ai_query");
          const agent = this.getAgent();
          const queryResult = await agent.aiQuery(prompt);
          details.query_result = queryResult;
          observed = `Midscene AI query completed: ${JSON.stringify(queryResult)}`;
          break;
        }

        default:
          outcome = "ERROR";
          errorCode = "UNSUPPORTED_ACTION";
          observed = `Unsupported UI action '${action}'`;
      }
    } catch (err: any) {
      outcome = err.name === "TimeoutError" ? "TIMED_OUT" : "ERROR";
      errorCode = err.code ?? (err.name === "TimeoutError" ? "UI_TIMEOUT" : "STEP_EXECUTION_ERROR");
      observed = `Action '${action}' failed: ${err.message || String(err)}`;

      // Automatically capture failure screenshot
      const shot = await this.evidenceCollector.captureScreenshot(this.page, run_id, test_id, step_index);
      if (shot) evidenceIds.push(shot);
    }

    const durationMs = Date.now() - startTime;
    return {
      protocol_version: "1.0",
      run_id,
      test_id,
      step_index,
      outcome,
      engine: action.startsWith("ai_") ? "midscene" : "playwright-node",
      duration_ms: durationMs,
      observed,
      error_code: errorCode,
      evidence_ids: evidenceIds,
      details: {
        ...details,
        console_errors: this.evidenceCollector.getConsoleErrors().slice(-5),
        failed_requests: this.evidenceCollector.getFailedRequests().slice(-5),
      },
    };
  }
}
