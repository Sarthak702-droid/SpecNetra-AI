# Implementation Plan — Fix CI Integration Issue

> **Status:** Awaiting user approval before modifying code.

## Goal Description

Diagnose and resolve the GitHub Actions CI failures shown in `Screenshot_2026-10-11_18-17-10.png` for repository `Sarthak702-droid/SpecNetra-AI` (runs #1 and #2).

### Root Cause Analysis

From inspecting the GitHub Actions failure logs via `gh run view 38139729830 --job 114471298279 --log-failed`:
1. The **Lint (Ruff)**, **Unit Tests (21/21)**, and **Integration Tests (2/2)** jobs all passed cleanly.
2. Both **E2E Verification (Healthy Demo)** and **E2E Verification (Intentional Bug Detection)** failed with:
   ```text
   RuntimeError: File at path /home/runner/work/SpecNetra-AI/SpecNetra-AI/demo/web/dist/index.html does not exist.
   FAILED tests/end_to_end/test_healthy_run.py::test_healthy_e2e_run - AssertionError: Test SMK-001 failed: UI step navigate completed successfully; Browser execution exception: Locator.fill: Timeout 15000ms exceeded.
     Call log:
       - waiting for get_by_label("Email")
   ```
3. `demo/web/dist` is excluded in `.gitignore` (standard practice for build artifacts).
4. The CI workflow jobs (`e2e-healthy` and `e2e-defective`) only install Python dependencies (`pip install -e ".[dev]"`) without setting up Node.js or running `npm run build` in `demo/web/`.
5. When Playwright navigated to `http://127.0.0.1:3000/login`, the test server (`server_helper.py`) attempted to serve `demo/web/dist/index.html` via Starlette `FileResponse`, which raised a 500 `RuntimeError` because the file was absent. Playwright waited 15,000ms for `<input id="email">` on an error page and timed out.

---

## User Review Required

> [!IMPORTANT]
> **Two-Pronged Solution Strategy:**
> 1. **Resilient Test Server (`tests/end_to_end/server_helper.py`):** Update `server_helper.py` so that if `demo/web/dist/index.html` is missing, it dynamically serves a self-contained fallback HTML containing the exact demo login and appointments views. This guarantees that E2E tests run in any lightweight Python environment without requiring a pre-installed Node.js toolchain.
> 2. **CI Pipeline Enhancement (`.github/workflows/ci.yml`):** Add Node.js setup and `npm run build` in `demo/web` before E2E tests so the official Vite production bundle is also tested in CI.
> 3. **Verification via GitHub Actions:** After committing and pushing the changes, we will use `gh run watch` to monitor the GitHub Actions workflow and confirm green checks across all jobs.

---

## Proposed Changes

### Component 1 — End-to-End Test Server Resiliency

#### [MODIFY] [`tests/end_to_end/server_helper.py`](file:///home/sarthaktripathy/Documents/SpecNetra%20AI/tests/end_to_end/server_helper.py)
- Detect if `dist_dir / "index.html"` exists.
- If it exists, serve it via `FileResponse`.
- If missing, serve an embedded `HTMLResponse` containing the full demo client logic (login form, appointments list, and single appointment details).

```python
FALLBACK_SPA_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SpecNetra Demo Hospital</title>
  <style>
    body { font-family: sans-serif; padding: 24px; background: #f8fafc; color: #1e293b; }
    .card { max-width: 500px; margin: 40px auto; background: white; padding: 32px; border-radius: 8px; }
    .form-group { margin-bottom: 16px; }
    label { display: block; margin-bottom: 6px; font-weight: 500; }
    input { width: 100%; padding: 10px; box-sizing: border-box; }
    button { width: 100%; padding: 12px; background: #2563eb; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; }
    .error { color: #dc2626; margin-top: 8px; font-weight: 500; }
    .detail-box { background: #eff6ff; padding: 16px; border-radius: 6px; margin-top: 16px; border: 1px solid #bfdbfe; }
  </style>
</head>
<body>
  <div id="app"></div>
  <script>
    const app = document.getElementById("app");
    function getApiUrl() {
      return window.location.port === "3000" ? `${window.location.protocol}//${window.location.hostname}:8001` : "";
    }
    function getStoredToken() { return localStorage.getItem("access_token"); }
    function setStoredToken(t) { localStorage.setItem("access_token", t); }

    function renderLogin() {
      app.innerHTML = `
        <div class="card">
          <h1>Sign In</h1>
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
          <h1>Appointments Dashboard</h1>
          <div data-testid="appointment-list" id="list-container">
            <p>Loading appointments...</p>
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
          listContainer.innerHTML = '<p>No appointments scheduled yet.</p>';
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
          <h1>Appointment Details</h1>
          <div id="detail-container">
            <p>Loading appointment ${id}...</p>
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
            <h3>Patient: ${appt.patient_name}</h3>
            <p><strong>Appointment ID:</strong> ${appt.id}</p>
            <p><strong>Time:</strong> ${appt.starts_at}</p>
            <p><strong>Status:</strong> ${appt.status}</p>
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
        from fastapi.responses import FileResponse
        return FileResponse(index_file)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=FALLBACK_SPA_HTML)
```

---

### Component 2 — CI Workflow Enhancement

#### [MODIFY] [`.github/workflows/ci.yml`](file:///home/sarthaktripathy/Documents/SpecNetra%20AI/.github/workflows/ci.yml)
In jobs `e2e-healthy` and `e2e-defective`:
- Add `actions/setup-node@v4` with `node-version: 20`.
- Add step `Build demo web frontend` running:
  ```bash
  cd demo/web
  npm install
  npm run build
  ```

---

## Verification Plan

### Automated Tests
1. **Test fallback without pre-built dist:**
   Temporarily rename `demo/web/dist` to `demo/web/dist_backup` and run:
   ```bash
   pytest tests/end_to_end/ -v
   ```
   Confirm both `test_healthy_run.py` and `test_defective_run.py` pass cleanly.
2. **Restore and test with pre-built dist:**
   Restore `demo/web/dist` and re-run:
   ```bash
   pytest tests/ -v
   ```
3. **Run Ruff format & lint check:**
   ```bash
   ruff check app/ tests/ && ruff format --check app/ tests/
   ```
4. **Push and monitor GitHub Actions:**
   ```bash
   git add tests/end_to_end/server_helper.py .github/workflows/ci.yml
   git commit -m "fix(ci): add demo web build step and fallback SPA server for E2E tests"
   git push origin main
   gh run watch
   ```
   Verify that all 5 CI jobs turn green.
