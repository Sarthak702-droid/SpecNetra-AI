import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from demo.api.main import app as api_app
from demo.api.routers.appointments import router as appointments_router
from demo.api.routers.auth import router as auth_router

# Create a simple SPA server for demo/web/dist with embedded fallback
web_app = FastAPI()
web_app.include_router(auth_router)
web_app.include_router(appointments_router)

dist_dir = Path(__file__).parent.parent.parent / "demo" / "web" / "dist"

if dist_dir.exists():
    web_app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

FALLBACK_SPA_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpecNetra · Autonomous QA</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: 'Inter', system-ui, -apple-system, sans-serif; padding: 0; margin: 0; background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%); color: #e2e8f0; min-height: 100vh; }
    .brand-header { text-align: center; padding: 40px 0 4px; font-size: 32px; font-weight: 800; background: linear-gradient(90deg, #06b6d4, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; letter-spacing: -0.5px; }
    .brand-sub { text-align: center; font-size: 11px; color: #64748b; margin-bottom: 32px; letter-spacing: 3px; text-transform: uppercase; font-weight: 500; }
    .card { max-width: 460px; margin: 0 auto; background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(16px); padding: 36px; border-radius: 20px; border: 1px solid rgba(6, 182, 212, 0.12); box-shadow: 0 0 60px rgba(6, 182, 212, 0.06), 0 8px 32px rgba(0,0,0,0.4); }
    h1 { margin: 0 0 24px; font-size: 22px; font-weight: 700; color: #f1f5f9; }
    .form-group { margin-bottom: 18px; }
    label { display: block; margin-bottom: 6px; font-weight: 600; font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
    input { width: 100%; padding: 12px 14px; background: rgba(15, 23, 42, 0.8); border: 1px solid #334155; border-radius: 10px; color: #e2e8f0; font-size: 15px; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
    input:focus { outline: none; border-color: #06b6d4; box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.12); }
    button { width: 100%; padding: 13px; background: linear-gradient(135deg, #06b6d4, #0891b2); color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; transition: transform 0.1s, box-shadow 0.2s; letter-spacing: 0.3px; }
    button:hover { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(6, 182, 212, 0.3); }
    .error { color: #f59e0b; margin-top: 10px; font-weight: 600; font-size: 14px; }
    .detail-box { background: rgba(6, 182, 212, 0.05); border: 1px solid rgba(6, 182, 212, 0.15); padding: 20px; border-radius: 14px; margin-top: 20px; }
    .detail-box p { margin: 6px 0; font-size: 14px; color: #cbd5e1; }
    .detail-box strong { color: #94a3b8; font-weight: 600; }
    a { color: #22d3ee; text-decoration: none; }
    a:hover { text-decoration: underline; }
    ul { list-style: none; padding: 0; margin: 0; }
    ul li { padding: 12px 16px; margin-bottom: 8px; background: rgba(15, 23, 42, 0.5); border-radius: 10px; border: 1px solid rgba(51, 65, 85, 0.5); }
  </style>
</head>
<body>
  <div class="brand-header">SpecNetra</div>
  <div class="brand-sub">Autonomous QA Intelligence</div>
  <div id="app"></div>
  <script>
    const app = document.getElementById("app");
    function getApiUrl() {
      return "";
    }
    function getStoredToken() { return localStorage.getItem("access_token"); }
    function setStoredToken(t) { localStorage.setItem("access_token", t); }

    function renderLogin() {
      app.innerHTML = `
        <div class="card">
          <h1>Welcome Back</h1>
          <form id="login-form">
            <div class="form-group">
              <label for="email">Email</label>
              <input type="email" id="email" name="email" required />
            </div>
            <div class="form-group">
              <label for="password">Password</label>
              <input type="password" id="password" name="password" required />
            </div>
            <button type="submit" role="button">Sign in</button>
            <div id="login-error" class="error" style="display: none;"></div>
          </form>
        </div>
      `;
      document.getElementById("login-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        const errEl = document.getElementById("login-error");
        try {
          const res = await fetch(`${getApiUrl()}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });
          if (!res.ok) {
            errEl.textContent = "Invalid email or password";
            errEl.style.display = "block";
            return;
          }
          const data = await res.json();
          setStoredToken(data.access_token);
          window.location.pathname = "/appointments";
        } catch (err) {
          errEl.textContent = "Network error connecting to API";
          errEl.style.display = "block";
        }
      });
    }

    async function renderAppointmentsList() {
      app.innerHTML = `
        <div class="card">
          <h1>Patient Schedule</h1>
          <div data-testid="appointment-list" id="list-container">
            <p style="color: #64748b;">Loading appointments...</p>
          </div>
        </div>
      `;
      const token = getStoredToken();
      const listContainer = document.getElementById("list-container");
      try {
        const res = await fetch(`${getApiUrl()}/api/appointments`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          listContainer.innerHTML = '<p class="error">Failed to load appointments</p>';
          return;
        }
        const data = await res.json();
        if (!data || data.length === 0) {
          listContainer.innerHTML = '<p style="color: #64748b;">No appointments scheduled yet.</p>';
        } else {
          listContainer.innerHTML = '<ul>' + data.map(a => `<li><a href="/appointments/${a.id}">${a.patient_name} - ${a.status}</a></li>`).join('') + '</ul>';
        }
      } catch (err) {
        listContainer.innerHTML = '<p class="error">API connection error</p>';
      }
    }

    async function renderAppointmentDetail(id) {
      app.innerHTML = `
        <div class="card">
          <h1>Visit Record</h1>
          <div id="detail-container">
            <p style="color: #64748b;">Loading appointment ${id}...</p>
          </div>
        </div>
      `;
      const token = getStoredToken();
      const container = document.getElementById("detail-container");
      try {
        const res = await fetch(`${getApiUrl()}/api/appointments/${id}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          container.innerHTML = '<div data-testid="appointment-not-found" class="error">Appointment not found or inaccessible.</div>';
          return;
        }
        const appt = await res.json();
        container.innerHTML = `
          <div data-testid="appointment-detail" class="detail-box">
            <h3 style="margin:0 0 8px;font-size:16px;color:#e2e8f0;">Patient: ${appt.patient_name}</h3>
            <p><strong>Appointment ID:</strong> ${appt.id}</p>
            <p><strong>Time:</strong> ${appt.starts_at}</p>
            <p><strong>Status:</strong> ${appt.status}</p>
            ${appt.reason ? `<p><strong>Reason:</strong> ${appt.reason}</p>` : ''}
          </div>
        `;
      } catch (err) {
        container.innerHTML = '<div data-testid="appointment-not-found" class="error">Error fetching appointment</div>';
      }
    }

    function router() {
      const path = window.location.pathname;
      if (path === "/login" || path === "/") {
        renderLogin();
      } else if (path === "/appointments") {
        renderAppointmentsList();
      } else if (path.startsWith("/appointments/")) {
        const id = path.replace("/appointments/", "").trim();
        renderAppointmentDetail(id);
      } else {
        renderLogin();
      }
    }
    window.addEventListener("DOMContentLoaded", router);
  </script>
</body>
</html>
"""


@web_app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_file = dist_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(content=FALLBACK_SPA_HTML)


@asynccontextmanager
async def run_demo_servers():
    api_config = uvicorn.Config(api_app, host="127.0.0.1", port=8001, log_level="warning")
    web_config = uvicorn.Config(web_app, host="127.0.0.1", port=3000, log_level="warning")

    api_server = uvicorn.Server(api_config)
    web_server = uvicorn.Server(web_config)

    api_task = asyncio.create_task(api_server.serve())
    web_task = asyncio.create_task(web_server.serve())

    # Wait until servers are up
    await asyncio.sleep(0.5)

    try:
        yield
    finally:
        api_server.should_exit = True
        web_server.should_exit = True
        await asyncio.gather(api_task, web_task, return_exceptions=True)
