import * as fs from "node:fs/promises";
import * as path from "node:path";
import { Page } from "playwright";

export interface EvidenceRecord {
  screenshotPath?: string;
  consoleErrors: string[];
  failedRequests: string[];
}

export class EvidenceCollector {
  private consoleErrors: string[] = [];
  private failedRequests: string[] = [];

  attach(page: Page): void {
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        this.consoleErrors.push(`[console.error] ${msg.text()}`);
      }
    });

    page.on("requestfailed", (req) => {
      this.failedRequests.push(
        `[net.failed] ${req.method()} ${req.url()}: ${
          req.failure()?.errorText || "unknown"
        }`
      );
    });
  }

  getConsoleErrors(): string[] {
    return [...this.consoleErrors];
  }

  getFailedRequests(): string[] {
    return [...this.failedRequests];
  }

  async captureScreenshot(
    page: Page,
    runId: string,
    testId: string,
    stepIndex: number,
    baseOutputDir: string = "output"
  ): Promise<string | undefined> {
    try {
      const runDir = path.resolve(baseOutputDir, runId, "screenshots");
      await fs.mkdir(runDir, { recursive: true });
      const filename = `${testId}_step${stepIndex}_${Date.now()}.png`;
      const fullPath = path.join(runDir, filename);
      await page.screenshot({ path: fullPath, fullPage: false });
      return fullPath;
    } catch {
      return undefined;
    }
  }

  clear(): void {
    this.consoleErrors = [];
    this.failedRequests = [];
  }
}
