import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.config import settings

app = FastAPI(
    title="SpecNetra AI · Autonomous QA Dashboard",
    version="1.0.0",
    description="Web Control Center for SpecNetra AI Autonomous Testing Framework",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"

_RUNNING_LOCK = asyncio.Lock()


class RunRequest(BaseModel):
    mode: str = "healthy"  # "healthy" or "bug"
    engine: str = "python"  # "python" or "midscene"


def read_latest_log() -> dict[str, Any] | None:
    log_file = OUTPUT_DIR / "execution_log.json"
    if log_file.exists():
        try:
            return json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def read_latest_report() -> str:
    report_file = OUTPUT_DIR / "report.md"
    if report_file.exists():
        return report_file.read_text(encoding="utf-8")
    return "No test reports generated yet. Click 'Launch Autonomous Test Run' to execute."


@app.get("/api/status")
async def get_status():
    log_data = read_latest_log()
    screenshots = []
    if SCREENSHOTS_DIR.exists():
        screenshots = [f.name for f in SCREENSHOTS_DIR.glob("*.png")]

    return {
        "status": "ready" if not _RUNNING_LOCK.locked() else "running",
        "api_url": settings.api_base_url,
        "web_url": settings.web_base_url,
        "ui_engine": settings.ui_engine,
        "environment": settings.target_environment,
        "last_run": log_data,
        "screenshots": screenshots,
    }


@app.get("/api/report")
async def get_report():
    return {"markdown": read_latest_report()}


@app.get("/api/execution-log")
async def get_execution_log():
    log_data = read_latest_log()
    if not log_data:
        raise HTTPException(status_code=404, detail="No execution log found")
    return log_data


@app.get("/screenshots/{filename}")
async def get_screenshot(filename: str):
    file_path = SCREENSHOTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(file_path, media_type="image/png")


@app.post("/api/run")
async def trigger_run(req: RunRequest):
    if _RUNNING_LOCK.locked():
        raise HTTPException(status_code=409, detail="A test run is already in progress")

    async with _RUNNING_LOCK:
        cmd = [
            str(PROJECT_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "app.main",
            "--requirements",
            "inputs/requirements.md",
            "--openapi",
            "inputs/openapi.json",
            "--scenarios",
            "inputs/scenarios.json",
            "--api-url",
            settings.api_base_url,
            "--web-url",
            settings.web_base_url,
        ]

        env = {
            "PATH": str(PROJECT_ROOT / ".venv" / "bin") + ":/usr/bin:/bin",
            "BROWSER_HEADLESS": "true",
            "UI_ENGINE": req.engine,
            "DEMO_BUG_MODE": "hide_created_appointment" if req.mode == "bug" else "",
        }

        import os

        merged_env = os.environ.copy()
        merged_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )

        stdout, stderr = await proc.communicate()
        exit_code = proc.returncode

        log_data = read_latest_log()
        report_md = read_latest_report()

        return {
            "exit_code": exit_code,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "run_result": log_data,
            "report_md": report_md,
        }


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpecNetra AI · Autonomous QA Control Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    :root {
      --bg: #090d16;
      --card-bg: rgba(17, 24, 39, 0.75);
      --card-border: rgba(6, 182, 212, 0.15);
      --accent-cyan: #06b6d4;
      --accent-violet: #a78bfa;
      --text-main: #f3f4f6;
      --text-muted: #94a3b8;
      --pass: #10b981;
      --fail: #ef4444;
      --blocked: #f59e0b;
    }
    body {
      font-family: 'Inter', system-ui, sans-serif;
      margin: 0; padding: 0;
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #090d16 60%, #030712 100%);
      color: var(--text-main);
      min-height: 100vh;
    }
    header {
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(20px);
      position: sticky; top: 0; z-index: 50;
      background: rgba(9, 13, 22, 0.8);
      padding: 16px 32px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .brand-group { display: flex; align-items: center; gap: 14px; }
    .logo-badge {
      width: 40px; height: 40px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent-cyan), var(--accent-violet));
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 20px; color: white;
      box-shadow: 0 0 24px rgba(6, 182, 212, 0.4);
    }
    .brand-title { font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }
    .brand-title span {
      background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .status-pill {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 14px; border-radius: 20px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      font-size: 12px; font-weight: 600; color: #34d399;
    }
    .pulse-dot {
      width: 8px; height: 8px; border-radius: 50%; background: #10b981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    main { max-width: 1300px; margin: 0 auto; padding: 32px 24px; }
    
    .stats-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }
    .stat-card {
      background: var(--card-bg); backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 16px; padding: 20px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    .stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
    .stat-value { font-size: 22px; font-weight: 700; margin-top: 6px; }

    .control-panel {
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
      border: 1px solid rgba(6, 182, 212, 0.25);
      border-radius: 20px; padding: 28px; margin-bottom: 28px;
      box-shadow: 0 0 50px rgba(6, 182, 212, 0.08);
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 20px;
    }
    .control-options { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
    .radio-pill-group {
      display: inline-flex; background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(51, 65, 85, 0.8);
      border-radius: 12px; padding: 4px;
    }
    .radio-label {
      padding: 8px 16px; border-radius: 8px; cursor: pointer;
      font-size: 13px; font-weight: 600; color: var(--text-muted);
      transition: all 0.2s;
    }
    .radio-label.active {
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.25), rgba(167, 139, 250, 0.25));
      color: white; border: 1px solid rgba(6, 182, 212, 0.4);
    }
    .btn-run {
      background: linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%);
      color: white; border: none; padding: 14px 32px; border-radius: 12px;
      font-size: 15px; font-weight: 700; cursor: pointer;
      box-shadow: 0 4px 25px rgba(6, 182, 212, 0.4);
      display: inline-flex; align-items: center; gap: 10px;
      transition: transform 0.15s, box-shadow 0.2s;
    }
    .btn-run:hover { transform: translateY(-2px); box-shadow: 0 6px 35px rgba(6, 182, 212, 0.6); }
    .btn-run:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

    .tabs { display: flex; gap: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); margin-bottom: 20px; }
    .tab-btn {
      background: none; border: none; padding: 12px 20px; color: var(--text-muted);
      font-size: 14px; font-weight: 600; cursor: pointer;
      border-bottom: 2px solid transparent; transition: all 0.2s;
    }
    .tab-btn.active { color: var(--accent-cyan); border-color: var(--accent-cyan); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { text-align: left; padding: 14px 16px; font-size: 12px; color: var(--text-muted); text-transform: uppercase; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
    td { padding: 14px 16px; font-size: 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .badge {
      display: inline-block; padding: 4px 10px; border-radius: 20px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
    }
    .badge-pass { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-fail { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-blocked { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }

    .terminal-box {
      background: #030712; border: 1px solid #1f2937;
      border-radius: 12px; padding: 20px;
      font-family: 'JetBrains Mono', monospace; font-size: 13px;
      color: #93c5fd; overflow-x: auto; max-height: 480px; line-height: 1.6;
    }
    .screenshot-card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 16px; padding: 20px; max-width: 600px; margin: 0 auto;
    }
    .screenshot-img { width: 100%; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.1); }
    .rca-card {
      background: rgba(239, 68, 68, 0.06); border: 1px solid rgba(239, 68, 68, 0.25);
      border-radius: 16px; padding: 24px; margin-bottom: 20px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand-group">
      <div class="logo-badge">S</div>
      <div>
        <div class="brand-title">SpecNetra <span>AI</span></div>
        <div style="font-size: 11px; color: var(--text-muted); letter-spacing: 1px; text-transform: uppercase;">Autonomous QA Intelligence Platform</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 16px;">
      <a href="http://localhost:3000" target="_blank" style="color: var(--accent-cyan); font-size: 13px; font-weight: 600; text-decoration: none;">Target App (Web) ↗</a>
      <a href="http://localhost:8001/docs" target="_blank" style="color: var(--accent-cyan); font-size: 13px; font-weight: 600; text-decoration: none;">Target API (Swagger) ↗</a>
      <div class="status-pill">
        <span class="pulse-dot"></span>
        <span id="agent-status-text">AGENT ONLINE</span>
      </div>
    </div>
  </header>

  <main>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Overall Verdict</div>
        <div class="stat-value" id="stat-verdict"><span class="badge badge-pass">PASSED</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Tests Executed</div>
        <div class="stat-value" id="stat-total">5</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Target Environment</div>
        <div class="stat-value" style="font-size: 17px; color: var(--accent-cyan);">staging (127.0.0.1)</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active UI Engine</div>
        <div class="stat-value" style="font-size: 17px; color: var(--accent-violet);">Playwright + Midscene</div>
      </div>
    </div>

    <div class="control-panel">
      <div class="control-options">
        <div>
          <div style="font-size: 13px; font-weight: 600; margin-bottom: 6px;">Execution Scenario</div>
          <div class="radio-pill-group">
            <span class="radio-label active" id="mode-healthy" onclick="setMode('healthy')">✓ Healthy Run</span>
            <span class="radio-label" id="mode-bug" onclick="setMode('bug')">🐞 Bug Catching Mode</span>
          </div>
        </div>
        <div>
          <div style="font-size: 13px; font-weight: 600; margin-bottom: 6px;">UI Engine</div>
          <div class="radio-pill-group">
            <span class="radio-label active" id="eng-python" onclick="setEngine('python')">Playwright (Fast)</span>
            <span class="radio-label" id="eng-midscene" onclick="setEngine('midscene')">Midscene AI Bridge</span>
          </div>
        </div>
      </div>
      <button class="btn-run" id="btn-launch" onclick="launchRun()">
        <span id="btn-icon">⚡</span>
        <span id="btn-text">Launch Autonomous Test Run</span>
      </button>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('tests')">📊 Test Cases Matrix</button>
      <button class="tab-btn" onclick="switchTab('rca')">🔍 Root Cause Analysis</button>
      <button class="tab-btn" onclick="switchTab('evidence')">📸 Captured Evidence</button>
      <button class="tab-btn" onclick="switchTab('report')">📋 Markdown Report</button>
      <button class="tab-btn" onclick="switchTab('terminal')">💻 Execution Log</button>
    </div>

    <!-- TAB 1: Tests -->
    <div id="tab-tests" class="tab-content active">
      <div class="stat-card" style="padding: 0; overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Test ID</th>
              <th>Requirements</th>
              <th>Outcome</th>
              <th>Duration</th>
              <th>Observed Evidence</th>
            </tr>
          </thead>
          <tbody id="tests-tbody">
            <tr><td colspan="5" style="text-align:center; padding: 24px; color: var(--text-muted);">Loading tests...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 2: RCA -->
    <div id="tab-rca" class="tab-content">
      <div id="rca-container">
        <div class="stat-card">
          <p style="color: var(--text-muted);">No active failures detected. All requirements pass specification constraints.</p>
        </div>
      </div>
    </div>

    <!-- TAB 3: Evidence -->
    <div id="tab-evidence" class="tab-content">
      <div id="evidence-container">
        <div class="screenshot-card">
          <h3 style="margin-top: 0;">Captured Failure Screenshot (SMK-003)</h3>
          <img src="/screenshots/SMK-003.png" class="screenshot-img" alt="Test Failure Screenshot" onerror="this.parentElement.innerHTML='<p style=\\'color:var(--text-muted)\\'>No failure screenshot captured (latest run was healthy).</p>'">
        </div>
      </div>
    </div>

    <!-- TAB 4: Report -->
    <div id="tab-report" class="tab-content">
      <div class="terminal-box" style="white-space: pre-wrap; color: #e2e8f0;" id="report-content">
        Loading verification report...
      </div>
    </div>

    <!-- TAB 5: Terminal -->
    <div id="tab-terminal" class="tab-content">
      <div class="terminal-box" id="terminal-content">
        Ready for autonomous execution.
      </div>
    </div>
  </main>

  <script>
    let currentMode = 'healthy';
    let currentEngine = 'python';

    function setMode(m) {
      currentMode = m;
      document.getElementById('mode-healthy').classList.toggle('active', m === 'healthy');
      document.getElementById('mode-bug').classList.toggle('active', m === 'bug');
    }

    function setEngine(e) {
      currentEngine = e;
      document.getElementById('eng-python').classList.toggle('active', e === 'python');
      document.getElementById('eng-midscene').classList.toggle('active', e === 'midscene');
    }

    function switchTab(t) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + t).classList.add('active');
    }

    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        if (data.last_run) {
          renderRunResults(data.last_run);
        }
      } catch (err) {
        console.error('Failed to load status', err);
      }
    }

    function renderRunResults(log) {
      const outcome = log.overall_outcome || 'UNKNOWN';
      const outcomeClass = outcome === 'PASSED' ? 'badge-pass' : 'badge-fail';
      document.getElementById('stat-verdict').innerHTML = `<span class="badge ${outcomeClass}">${outcome}</span>`;
      
      const tests = log.tests || [];
      document.getElementById('stat-total').textContent = tests.length;

      const tbody = document.getElementById('tests-tbody');
      if (tests.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 24px;">No tests in log</td></tr>';
        return;
      }

      tbody.innerHTML = tests.map(t => {
        const badge = t.outcome === 'PASSED' ? 'badge-pass' : t.outcome === 'FAILED' ? 'badge-fail' : 'badge-blocked';
        return `
          <tr>
            <td style="font-weight: 600; font-family: 'JetBrains Mono', monospace;">${t.test_id}</td>
            <td style="color: var(--text-muted);">${(t.requirement_ids || []).join(', ')}</td>
            <td><span class="badge ${badge}">${t.outcome}</span></td>
            <td style="color: var(--text-muted);">${(t.duration_ms || 0).toFixed(1)}ms</td>
            <td style="font-size: 13px; color: #cbd5e1;">${t.observed || 'Completed'}</td>
          </tr>
        `;
      }).join('');

      document.getElementById('terminal-content').textContent = JSON.stringify(log, null, 2);

      // Check RCA
      const failed = tests.filter(t => t.outcome === 'FAILED');
      const rcaContainer = document.getElementById('rca-container');
      if (failed.length > 0) {
        rcaContainer.innerHTML = failed.map(f => `
          <div class="rca-card">
            <h3 style="color: #f87171; margin-top:0;">⚠️ Detected Defect in ${f.test_id}</h3>
            <p><strong>Observed Evidence:</strong> ${f.observed}</p>
            <p><strong>Hypothesis:</strong> Frontend data-loading, rendering synchronization, or backend record availability mismatch</p>
            <p><strong>Confidence:</strong> HIGH</p>
            <p><strong>Action:</strong> Inspect appointment retrieval and DOM visibility</p>
          </div>
        `).join('');
      } else {
        rcaContainer.innerHTML = '<div class="stat-card"><p style="color: var(--text-muted);">✓ No failures detected in latest run. Application is performing within requirements.</p></div>';
      }
    }

    async function loadReport() {
      try {
        const res = await fetch('/api/report');
        const data = await res.json();
        document.getElementById('report-content').textContent = data.markdown;
      } catch (err) {}
    }

    async function launchRun() {
      const btn = document.getElementById('btn-launch');
      const text = document.getElementById('btn-text');
      const icon = document.getElementById('btn-icon');
      
      btn.disabled = true;
      icon.textContent = '⏳';
      text.textContent = 'Executing Pipeline (AI Planning & Browser Actions)...';

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: currentMode, engine: currentEngine })
        });
        const data = await res.json();
        
        if (data.run_result) {
          renderRunResults(data.run_result);
        }
        if (data.report_md) {
          document.getElementById('report-content').textContent = data.report_md;
        }
        
        // Refresh evidence tab
        document.getElementById('evidence-container').innerHTML = `
          <div class="screenshot-card">
            <h3 style="margin-top: 0;">Captured Failure Screenshot (SMK-003)</h3>
            <img src="/screenshots/SMK-003.png?t=${Date.now()}" class="screenshot-img" alt="Test Failure Screenshot" onerror="this.parentElement.innerHTML='<p style=\\'color:var(--text-muted)\\'>No failure screenshot captured in this run (Target was healthy).</p>'">
          </div>
        `;
      } catch (err) {
        alert('Run failed: ' + err.message);
      } finally {
        btn.disabled = false;
        icon.textContent = '⚡';
        text.textContent = 'Launch Autonomous Test Run';
      }
    }

    loadStatus();
    loadReport();
    setInterval(loadStatus, 5000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)


def main():
    parser = argparse.ArgumentParser(description="SpecNetra AI Web Control Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the dashboard on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the dashboard to")
    args = parser.parse_args()

    print(f"Starting SpecNetra AI Control Dashboard on http://{args.host}:{args.port}")
    uvicorn.run("app.dashboard:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
