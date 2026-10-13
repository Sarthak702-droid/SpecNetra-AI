import { chromium, Browser, BrowserContext, Page } from "playwright";
import { SessionCreateRequest } from "./schemas.js";
import { EvidenceCollector } from "./evidence.js";
import { StepExecutor } from "./step-executor.js";

export class Session {
  readonly id: string;
  readonly runId: string;
  private browser: Browser;
  private context: BrowserContext;
  private page: Page;
  private evidenceCollector: EvidenceCollector;
  private executor: StepExecutor;
  private closed = false;

  private constructor(
    id: string,
    runId: string,
    browser: Browser,
    context: BrowserContext,
    page: Page,
    evidenceCollector: EvidenceCollector,
    allowedHosts: string[]
  ) {
    this.id = id;
    this.runId = runId;
    this.browser = browser;
    this.context = context;
    this.page = page;
    this.evidenceCollector = evidenceCollector;
    this.executor = new StepExecutor(page, evidenceCollector, allowedHosts);
  }

  static async create(req: SessionCreateRequest): Promise<Session> {
    const sessionId = `sess_${Math.random().toString(36).substring(2, 10)}`;
    const browser = await chromium.launch({
      headless: req.headless,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });

    const context = await browser.newContext({
      viewport: req.viewport,
      ignoreHTTPSErrors: true,
    });

    const page = await context.newPage();
    const evidenceCollector = new EvidenceCollector();
    evidenceCollector.attach(page);

    return new Session(
      sessionId,
      req.run_id,
      browser,
      context,
      page,
      evidenceCollector,
      req.allowed_hosts
    );
  }

  getExecutor(): StepExecutor {
    if (this.closed) throw new Error(`Session ${this.id} is closed`);
    return this.executor;
  }

  async close(): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    try {
      await this.executor.destroy();
    } catch {}
    try {
      await this.page.close();
    } catch {}
    try {
      await this.context.close();
    } catch {}
    try {
      await this.browser.close();
    } catch {}
  }
}

export class SessionManager {
  private sessions = new Map<string, Session>();

  async createSession(req: SessionCreateRequest): Promise<Session> {
    const session = await Session.create(req);
    this.sessions.set(session.id, session);
    return session;
  }

  getSession(id: string): Session | undefined {
    return this.sessions.get(id);
  }

  async closeSession(id: string): Promise<boolean> {
    const session = this.sessions.get(id);
    if (!session) return false;
    await session.close();
    this.sessions.delete(id);
    return true;
  }

  async closeAll(): Promise<void> {
    const active = Array.from(this.sessions.values());
    this.sessions.clear();
    await Promise.all(active.map((s) => s.close()));
  }
}
