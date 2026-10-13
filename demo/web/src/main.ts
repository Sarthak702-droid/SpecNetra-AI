const app = document.getElementById("app")!;

function getApiUrl(): string {
  return "";
}

function getStoredToken(): string | null {
  return localStorage.getItem("access_token");
}

function setStoredToken(token: string) {
  localStorage.setItem("access_token", token);
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "confirmed") return "status-confirmed";
  if (s === "completed") return "status-completed";
  if (s === "cancelled") return "status-cancelled";
  return "status-scheduled";
}

function renderLogin() {
  app.innerHTML = `
    <div class="card">
      <h1>Welcome Back</h1>
      <form id="login-form">
        <div class="form-group">
          <label for="email">Email</label>
          <input type="email" id="email" name="email" placeholder="you@clinic.com" required />
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" placeholder="••••••••" required />
        </div>
        <button type="submit" role="button">Sign in</button>
        <div id="login-error" class="error" style="display: none;"></div>
      </form>
    </div>
  `;

  const form = document.getElementById("login-form") as HTMLFormElement;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = (document.getElementById("email") as HTMLInputElement).value;
    const password = (document.getElementById("password") as HTMLInputElement).value;
    const errEl = document.getElementById("login-error")!;

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
  const listContainer = document.getElementById("list-container")!;

  try {
    const res = await fetch(`${getApiUrl()}/api/appointments`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      listContainer.innerHTML = `<p class="error">Failed to load appointments</p>`;
      return;
    }
    const data = await res.json();
    if (!data || data.length === 0) {
      listContainer.innerHTML = `<p style="color: #64748b;">No appointments scheduled yet.</p>`;
    } else {
      listContainer.innerHTML = `
        <ul>
          ${data.map((a: any) => `<li><a href="/appointments/${a.id}">${a.patient_name}</a> <span class="status-badge ${statusBadgeClass(a.status)}">${a.status}</span></li>`).join("")}
        </ul>
      `;
    }
  } catch (err) {
    listContainer.innerHTML = `<p class="error">API connection error</p>`;
  }
}

async function renderAppointmentDetail(id: string) {
  app.innerHTML = `
    <div class="card">
      <a href="/appointments" class="back-link">← Back to schedule</a>
      <h1>Visit Record</h1>
      <div id="detail-container">
        <p style="color: #64748b;">Loading appointment ${id}...</p>
      </div>
    </div>
  `;

  const token = getStoredToken();
  const container = document.getElementById("detail-container")!;

  try {
    const res = await fetch(`${getApiUrl()}/api/appointments/${id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!res.ok) {
      container.innerHTML = `
        <div data-testid="appointment-not-found" class="error">
          Appointment not found or inaccessible.
        </div>
      `;
      return;
    }

    const appt = await res.json();
    container.innerHTML = `
      <div data-testid="appointment-detail" class="detail-box">
        <h3>Patient: ${appt.patient_name}</h3>
        <p><strong>Appointment ID:</strong> ${appt.id}</p>
        <p><strong>Time:</strong> ${appt.starts_at}</p>
        <p><strong>Status:</strong> <span class="status-badge ${statusBadgeClass(appt.status)}">${appt.status}</span></p>
        ${appt.reason ? `<p><strong>Reason:</strong> ${appt.reason}</p>` : ""}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div data-testid="appointment-not-found" class="error">Error fetching appointment</div>`;
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
