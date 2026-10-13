# System Requirements: Public Live Booking Platform

This document specifies the core API and UI functional requirements for the public live booking platform (`restful-booker.herokuapp.com` and `automationintesting.online`).

## REQ-PUB-001 — Administrative Authentication
Priority: P0
- The system must provide an authentication endpoint (`POST /auth`) for administrators.
- When provided with valid credentials (`admin` / `password123`), the platform must issue an authentication token (`token`).

## REQ-PUB-002 — Booking Lifecycle Management
Priority: P0
- Authorized clients must be able to create new hotel bookings (`POST /booking`).
- Successful booking creation must return a unique `bookingid` and confirm the booking payload details.

## REQ-PUB-003 — Web Portal Availability and Rendering
Priority: P0
- The public customer booking portal (`automationintesting.online`) must load successfully over HTTPS.
- The web application root container must render and be visible to end users.

## REQ-PUB-004 — Input Validation and Error Handling
Priority: P1
- The system must safely handle invalid credentials, returning an explicit rejection message without crashing or exposing stack traces.
- Querying a non-existent booking record (`GET /booking/{invalid_id}`) must return HTTP 404 Not Found.
