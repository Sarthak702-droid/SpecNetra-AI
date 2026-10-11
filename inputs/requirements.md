# SpecNetra Demo Application Requirements

## REQ-001 — User Authentication
Priority: P0
- A registered user can log in with valid email and password credentials via POST /api/auth/login.
- Successful login returns HTTP 200 with a bearer access token and token_type 'bearer'.
- The system rejects invalid credentials with HTTP 401 and an error code 'INVALID_CREDENTIALS'.
- After login, GET /api/me returns the authenticated user's profile and confirms active session.

## REQ-002 — Appointment Creation and UI Visibility
Priority: P0
- An authenticated user can create an appointment via POST /api/appointments with patient_name, starts_at, and reason.
- The creation endpoint returns HTTP 201 with status 'confirmed' and a generated non-empty appointment ID.
- The created appointment must be visible in the web browser at /appointments/{appointment_id} displaying the patient's name.

## REQ-003 — Appointment Input Validation
Priority: P1
- The API must reject appointment creation requests missing mandatory fields (e.g. empty patient_name or missing starts_at).
- Validation failures return HTTP 422 with field-level error details.
