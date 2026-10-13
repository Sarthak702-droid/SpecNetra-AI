import * as http from "node:http";
import "dotenv/config";
import { SessionManager } from "./session-manager.js";
import { SessionCreateRequestSchema, UiCommandSchema } from "./schemas.js";

const PORT = parseInt(process.env.WORKER_PORT || "0", 10);
const AUTH_TOKEN = process.env.WORKER_AUTH_TOKEN || "";

const sessionManager = new SessionManager();

function readJsonBody(req: http.IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 5 * 1024 * 1024) {
        reject(new Error("Request payload too large"));
      }
    });
    req.on("end", () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (err) {
        reject(new Error("Malformed JSON"));
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res: http.ServerResponse, status: number, data: any): void {
  const json = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(json),
  });
  res.end(json);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
  const pathname = url.pathname;
  const method = req.method?.toUpperCase();

  // Public health endpoint
  if (method === "GET" && pathname === "/health") {
    return sendJson(res, 200, { status: "ok", timestamp: new Date().toISOString() });
  }

  // Auth gate
  if (AUTH_TOKEN) {
    const authHeader = req.headers.authorization;
    if (!authHeader || authHeader !== `Bearer ${AUTH_TOKEN}`) {
      return sendJson(res, 401, { error: "UNAUTHORIZED", message: "Invalid or missing bearer token" });
    }
  }

  try {
    // 1. Create Session: POST /v1/session
    if (method === "POST" && pathname === "/v1/session") {
      const rawBody = await readJsonBody(req);
      const parsed = SessionCreateRequestSchema.safeParse(rawBody);
      if (!parsed.success) {
        return sendJson(res, 400, { error: "VALIDATION_ERROR", details: parsed.error.issues });
      }
      const session = await sessionManager.createSession(parsed.data);
      return sendJson(res, 201, {
        session_id: session.id,
        run_id: session.runId,
        status: "READY",
      });
    }

    // 2. Step Execution: POST /v1/session/:id/step
    const stepMatch = pathname.match(/^\/v1\/session\/([^/]+)\/step$/);
    if (method === "POST" && stepMatch) {
      const sessionId = stepMatch[1];
      const session = sessionManager.getSession(sessionId);
      if (!session) {
        return sendJson(res, 404, { error: "SESSION_NOT_FOUND", message: `Session ${sessionId} not found` });
      }

      const rawBody = await readJsonBody(req);
      const parsed = UiCommandSchema.safeParse(rawBody);
      if (!parsed.success) {
        return sendJson(res, 400, { error: "VALIDATION_ERROR", details: parsed.error.issues });
      }

      const executor = session.getExecutor();
      const result = await executor.execute(parsed.data);
      return sendJson(res, 200, result);
    }

    // 3. Delete Session: DELETE /v1/session/:id
    const deleteMatch = pathname.match(/^\/v1\/session\/([^/]+)$/);
    if (method === "DELETE" && deleteMatch) {
      const sessionId = deleteMatch[1];
      const closed = await sessionManager.closeSession(sessionId);
      if (!closed) {
        return sendJson(res, 404, { error: "SESSION_NOT_FOUND", message: `Session ${sessionId} not found` });
      }
      return sendJson(res, 200, { message: `Session ${sessionId} closed successfully` });
    }

    // 404 Not Found
    return sendJson(res, 404, { error: "NOT_FOUND", message: `Route ${method} ${pathname} not found` });
  } catch (err: any) {
    return sendJson(res, 500, { error: "INTERNAL_ERROR", message: err.message || String(err) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  const addr = server.address();
  const actualPort = typeof addr === "object" && addr ? addr.port : PORT;
  // Output line format expected by Python worker spawner:
  console.log(`[WORKER_READY] PORT=${actualPort}`);
});

async function shutdown(): Promise<void> {
  console.log("[WORKER] Shutting down sessions and server...");
  await sessionManager.closeAll();
  server.close(() => {
    process.exit(0);
  });
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
