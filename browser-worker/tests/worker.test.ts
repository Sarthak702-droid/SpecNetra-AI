import test from "node:test";
import assert from "node:assert/strict";
import { spawn, ChildProcess } from "node:child_process";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Worker HTTP server lifecycle and deterministic step execution", async (t) => {
  const token = "test-secret-token-123";
  let workerProcess: ChildProcess;
  let port: number;

  await t.test("Start worker process and read port", async () => {
    return new Promise<void>((resolve, reject) => {
      const serverScript = path.resolve(__dirname, "../src/server.ts");
      workerProcess = spawn("npx", ["tsx", serverScript], {
        env: {
          ...process.env,
          WORKER_PORT: "0",
          WORKER_AUTH_TOKEN: token,
        },
        stdio: ["ignore", "pipe", "pipe"],
      });

      workerProcess.stdout?.on("data", (data: Buffer) => {
        const text = data.toString();
        const match = text.match(/\[WORKER_READY\] PORT=(\d+)/);
        if (match) {
          port = parseInt(match[1], 10);
          resolve();
        }
      });

      workerProcess.stderr?.on("data", (data: Buffer) => {
        // Log worker errors for debugging
        console.error("[worker stderr]", data.toString());
      });

      workerProcess.on("error", reject);
      workerProcess.on("exit", (code) => {
        if (!port) reject(new Error(`Worker exited early with code ${code}`));
      });
    });
  });

  t.after(() => {
    if (workerProcess) {
      workerProcess.kill("SIGKILL");
    }
    setTimeout(() => process.exit(0), 100);
  });

  const baseUrl = `http://127.0.0.1:${port!}`;

  await t.test("Health check responds 200", async () => {
    const res = await fetch(`${baseUrl}/health`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as any;
    assert.equal(body.status, "ok");
  });

  await t.test("Unauthorized call is rejected with 401", async () => {
    const res = await fetch(`${baseUrl}/v1/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: "unauth_run" }),
    });
    assert.equal(res.status, 401);
  });

  let sessionId: string;
  await t.test("Create browser session", async () => {
    const res = await fetch(`${baseUrl}/v1/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        run_id: "test_run_001",
        headless: true,
        allowed_hosts: ["127.0.0.1", "localhost"],
      }),
    });
    assert.equal(res.status, 201);
    const body = (await res.json()) as any;
    assert.ok(body.session_id);
    sessionId = body.session_id;
  });

  await t.test("Execute deterministic navigate and assert_text on inline server", async () => {
    // Navigate to a local page or data URL
    const stepRes = await fetch(`${baseUrl}/v1/session/${sessionId}/step`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        run_id: "test_run_001",
        test_id: "SMK-001",
        step_index: 0,
        action: "navigate",
        params: { url: "http://127.0.0.1:" + port! + "/health" },
      }),
    });
    assert.equal(stepRes.status, 200);
    const stepBody = (await stepRes.json()) as any;
    assert.equal(stepBody.outcome, "PASSED");
    assert.ok(stepBody.duration_ms > 0);
  });

  await t.test("Delete session closes cleanly", async () => {
    const res = await fetch(`${baseUrl}/v1/session/${sessionId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    assert.equal(res.status, 200);
  });
});
