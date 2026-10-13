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
      <h1>Appointments Dashboard</h1>
      <div data-testid="appointment-list" id="list-container">
        <p>Loading appointments...</p>
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
      listContainer.innerHTML = `<p>No appointments scheduled yet.</p>`;
    } else {
      listContainer.innerHTML = `
        <ul>
          ${data.map((a: any) => `<li><a href="/appointments/${a.id}">${a.patient_name} - ${a.status}</a></li>`).join("")}
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
      <h1>Appointment Details</h1>
      <div id="detail-container">
        <p>Loading appointment ${id}...</p>
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
        <p><strong>Status:</strong> ${appt.status}</p>
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
