# CareGrid HMS

CareGrid is being built as a modular-monolith hospital management system for private hospital deployments. The initial prototype follows the supplied desktop-style references: grouped left navigation, contextual actions, compact status indicators, and data-dense searchable tables. The interface uses synthetic data only.

## Architecture baseline

- **Frontend:** React + TypeScript + Ant Design.
- **Backend:** Python 3.13 + FastAPI.
- **Primary datastore:** PostgreSQL 16+. It will be the authoritative store for patient, clinical, and financial records.
- **Live updates:** WebSockets/SignalR-style events will be added behind authenticated APIs when a workflow needs them.
- **Caching:** Redis is intentionally not part of the first slice; introduce it only for measured caching or coordination needs.
- **Structure:** Modular monolith, with capability boundaries for identity, patient access, clinical care, inpatient, billing, inventory, workforce, and reporting.

The first slice includes a synthetic-data UI prototype, API health checks, session-based login, server-side permission checks, login lockout, and a PostgreSQL foundation migration for users, roles, permissions, sessions, and audit records. The UI is not yet connected to authentication or live data, and audit coverage is currently limited to identity/session events. Clinical, patient, and financial workflows, MFA, full audit coverage, and production hardening are not complete. Do not connect this prototype to real patient, staff, or payment data or expose it to a network.

## Run the frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

The queue contains synthetic sample records. It is not connected to a backend.

## Run the backend

Python 3.12 or newer is required. From the repository root:

```powershell
Set-Location backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`GET /api/v1/health/live` confirms the process is running. Readiness reports that PostgreSQL is not configured until `HMS_DATABASE_URL` is set. Authentication uses a random opaque, server-side session cookie (stored as a hash), a readable CSRF cookie/header pair, and Argon2id password hashes. No default credentials or production secrets are provided.

## Database

`backend/migrations/001_core.sql` defines the initial identity, permission, session, and append-only audit-log tables and seeds least-privilege role permissions. It is a PostgreSQL migration and has not been applied or tested against a running PostgreSQL server in this workspace. After applying it and setting `HMS_DATABASE_URL`, run `.\.venv\Scripts\python.exe -m app.bootstrap_admin` from `backend` to create the first administrator interactively. The authentication API provides `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `GET /api/v1/auth/users` (requires `identity.users.read`), and CSRF-protected `POST /api/v1/auth/logout`.

## Development sequence

1. Foundation: identity, permission enforcement, audit pipeline, and application shell.
2. Patient registration, duplicate review, appointments, and reception queue.
3. Clinical encounters, nursing, diagnostics, and results.
4. Billing, payments, receipts, corrections, approvals, and reconciliation.
5. Admissions, wards, bed allocation, transfers, and discharge.
6. Pharmacy, inventory, procurement, and stock audit.
7. Accounting, workforce, insurance, and reporting.
8. External integrations, security testing, recovery drills, and deployment hardening.

Before any real deployment, complete threat modeling, applicable Kenyan legal/privacy review, role and permission design, encrypted backup/restore drills, infrastructure hardening, and independent security testing.
