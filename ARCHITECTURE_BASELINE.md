# TETHER Baseline Architecture Report

- **Task:** Phase 0, Task 0.1 — Repository architecture inspection
- **Assessment date:** 16 November 2026
- **Branch and revision:** `main` at `a055824`
- **Repository state at inspection:** 51 tracked files; clean worktree

## Executive summary

TETHER is a small monorepo with a React/TypeScript single-page frontend and a Python/FastAPI backend. It is implemented as a modular-monolith starter, but the backend currently has only health, identity/RBAC, and patient-access API routers. Persisted operational functionality is limited to patient registration/search/update and the OPD visit queue.

SQLite is the active development database. Numbered PostgreSQL SQL files describe a prospective schema, but they are not managed by a migration runner and have not been verified against PostgreSQL. There is no Docker Compose setup, CI workflow, production deployment configuration, or frontend test suite. The application is a development demonstrator, not a hospital-ready HMIS.

## Repository layout

The inventory contains 51 tracked files:

- Root: workspace/package manifests, lockfile, `.gitignore`, setup documentation, current-state report, and VS Code settings.
- `backend/app/api/`: FastAPI health, authentication/authorization, and patient-access routes.
- `backend/app/core/`: Pydantic settings and the role/permission catalog.
- `backend/app/db/`: SQLAlchemy models and asynchronous engine/session setup.
- `backend/migrations/`: four hand-authored PostgreSQL SQL migrations.
- `backend/tests/`: authentication, RBAC, health, owner-recovery, and patient-access tests.
- `frontend/src/`: app shell, API wrapper, administration console, patient/OPD screens, and styles.
- `frontend/public/` and `frontend/src/assets/`: icons and inherited Vite/React starter assets.

The local `backend/.env` and SQLite database are not tracked. No credential values or database records were included in this inspection.

## Runtime architecture and data flow

1. The browser loads the React application from Vite.
2. `App.tsx` checks the existing session through `GET /api/v1/auth/me`, builds a permission-filtered navigation menu, and selects either the administration console, patient/OPD screens, or a placeholder.
3. Frontend requests use `api.ts`, `fetch`, and `credentials: include`. Mutating requests send the CSRF token from the readable cookie in `X-CSRF-Token`.
4. FastAPI mounts the health, authentication, and patient-access routers beneath `/api/v1`. CORS is configured from `HMS_CORS_ORIGINS`.
5. Authentication dependencies validate the opaque session cookie, expiration, revocation, and active account. Writes validate CSRF. Permission dependencies enforce RBAC server-side and append authorization audit events.
6. API handlers use an asynchronous SQLAlchemy session from `get_db`, persist domain records and audit events, and return JSON payloads.

The FastAPI lifespan currently disposes the engine on shutdown; it does not apply schema migrations or create production tables at startup. `/health/live` is process-only, while `/health/ready` performs `SELECT 1` against the configured database.

## Backend domains and APIs

### Identity and access control

`auth.py` implements login/logout/current-user handling, users, roles, permissions, per-user permission overrides, password resets, account status, audit viewing, and system-owner safeguards. The code uses Argon2 password hashes, random opaque session/CSRF tokens stored as hashes, HttpOnly/SameSite cookies, and configurable per-account failed-login lockout. Defaults are five failed attempts and a 15-minute lockout.

The permission catalog is generated from a role/function matrix. It currently defines 33 roles and 410 catalog permissions. Users can hold multiple roles; explicit individual denies override role grants, while the system owner/SuperAdmin bypasses permission checks. The designated owner is represented by a unique `is_system_owner` database flag and has a trusted-host CLI recovery path.

### Patient access

`patient_access.py` exposes:

- Patient search/list, registration, single-record read, and update.
- OPD visit queue listing and visit creation linked to a patient.

Search and list endpoints are paginated. Patient numbers and visit numbers are generated from UUIDs. Registration/update validation includes basic name, phone, email, date, and sex-at-birth constraints. Likely duplicates are rejected for manual review based on matching phone or name/date-of-birth. Patient and OPD operations have permission checks and audit events.

The current data model includes users, roles, permissions, user-role and role-permission joins, individual permission overrides, auth sessions, audit logs, patients, and outpatient visits. It does not yet model encounters, appointments, patient history/merges, facilities, wards/beds, diagnoses, clinical notes, tests/results, medication, invoices, claims, inventory, staff records, or reporting facts.

### Other clinical and operational domains

The permission catalog and frontend navigation contain entries for additional departments, but those entries do not correspond to implemented domain APIs or database models. In the frontend, these currently route to a placeholder screen. No admissions/IPD, clinical documentation, nursing, laboratory, radiology, theatre, pharmacy, billing, SHA/insurance, accounting, procurement/inventory, HR, or operational-reporting workflows are present.

## Frontend architecture

The frontend is a Vite/React SPA using TypeScript, React 19, and Ant Design. Navigation and page selection are handled by local React state in `App.tsx`; there is no client-side routing library. Implemented screens are:

- Login and authenticated application shell.
- User/role/permission and audit administration.
- Patient registration/search/update and OPD queue/visit creation.

Other navigation items display placeholders. Some shell values, including the displayed facility, date, and notification count, are static. The error-handling API wrapper reports network and HTTP errors, but there is no frontend component test or browser automation suite in the repository.

## Persistence and migrations

The active development configuration uses SQLite through `aiosqlite`. SQLAlchemy also has an `asyncpg` dependency for PostgreSQL, and the README names PostgreSQL 16+ as the intended primary datastore.

The four numbered SQL files are PostgreSQL-oriented:

1. `001_core.sql`: identity, sessions, role/permission joins, audit log and an append-only audit trigger, plus legacy seed data.
2. `002_user_permission_overrides.sql`: department and individual permission overrides.
3. `003_patient_access.sql`: patients and outpatient visits.
4. `004_system_owner.sql`: system-owner marker and unique partial index.

There is no Alembic configuration, migration-version table, automated upgrade runner, or demonstrated clean-database/upgrade test on PostgreSQL. SQLite schema creation and additive updates are handled separately by `bootstrap_roles.py`; they do not establish parity with the PostgreSQL scripts.

## Build, tests, and operational tooling

- Backend: Python package declared in `backend/pyproject.toml`; pytest and Ruff are optional development dependencies. Tests use FastAPI `TestClient` and temporary SQLite databases.
- Frontend: npm workspace with a lockfile; `npm run build` runs `tsc -b` and Vite. Oxlint is configured. No frontend unit, integration, or e2e test runner is configured.
- The last known validation from the preceding implementation work was 19 passing backend tests and Ruff success; frontend build passed with four React effect lint warnings and a bundle-size warning. These checks were not rerun as part of this inspection-only task.
- No Dockerfile, Compose file, GitHub Actions workflow, deployment manifests, monitoring setup, or production runbook is tracked.

## Baseline risks and inconsistencies

1. **Database lifecycle:** PostgreSQL is the stated target, but SQLite is the only database verified in this workspace. Migration execution, rollback, backups, restore, and database concurrency behavior are unverified.
2. **Migration management:** Hand-authored SQL and SQLite bootstrap logic are separate mechanisms without a shared versioned migration system.
3. **Scope of authorization:** RBAC is present, but there is no facility/department/patient-context access-control model. Most catalog permissions currently have no matching domain endpoint.
4. **Clinical and financial readiness:** Clinical records, billing, insurance, medications, inventory, accounting, and associated workflows are absent. Do not use real patient, staff, clinical, or payment data.
5. **Audit coverage:** Current events cover identity and the initial patient/OPD slice. PostgreSQL has an audit mutation-rejecting trigger; equivalent SQLite immutability and external tamper evidence are not verified.
6. **Authentication hardening:** There is no MFA, centralized IP/device rate limiting, web self-service recovery, or session-management UI. The owner recovery command requires trusted local access.
7. **Frontend quality controls:** There is no automated frontend test suite or browser-test harness. Several shell values are static, and nonimplemented modules still appear as placeholders.
8. **Version/document drift:** `pyproject.toml` permits Python 3.12+, while the README says Python 3.13+. `CURRENT_STATE_REPORT.md` still identifies revision `14eaff8`, describes a dirty worktree, and contains mixed statements about browser verification; this inspection is at `a055824` with a clean worktree.
9. **Starter residue:** `frontend/README.md` is the stock Vite/React guide, and Vite/React sample assets remain in the frontend.

## Phase 0, Task 0.3 verification

**Date:** 16 November 2026

- The frontend returned HTTP 200 and rendered the TETHER login page in the shared browser.
- `/api/v1/health/live` and `/api/v1/health/ready` returned HTTP 200; the active configured database backend is SQLite.
- An unauthenticated `GET /api/v1/auth/me` returned HTTP 401 with CORS headers allowing the frontend origin and credentials, as expected for the logged-out page.
- Backend tests passed: 19 passed. Ruff reported no issues. These tests use synthetic users and temporary SQLite databases and cover login/logout, CSRF, permission enforcement, system-owner policies, recovery, account lockout, and patient/OPD access.
- Frontend TypeScript/Vite build passed. It emitted the existing large-chunk warning (1,051.73 kB minified JavaScript). Oxlint exited successfully with four `react(set-state-in-effect)` warnings. No frontend automated test runner is configured.
- The browser login fields initially contained prefilled values. They were cleared on the user's instruction and were not used for authentication. The application source initializes both fields empty; whether the initial values came from browser autofill or retained browser state is unverified.
- PostgreSQL and its migrations were not exercised in this task.

## Phase 0, Task 0.4 verification

**Date:** 16 November 2026

- PostgreSQL 16+ is documented as the supported development/production target, with `postgresql+asyncpg://` as the required async URL form. The local SQLite database remains active; no database URL or persisted data was changed.
- The backend test constructs a PostgreSQL async engine and compiles all SQLAlchemy tables and indexes with the PostgreSQL dialect without connecting to a server.
- Backend tests passed: 20 passed. Ruff passed. The frontend build passed; the existing large-chunk warning and four Oxlint effect warnings remain.
- No local PostgreSQL server is available, so database connection, migration execution, and end-to-end PostgreSQL integration remain unverified. Raw SQL migrations are unchanged; Alembic is still deferred to Task 0.6.

## Phase 0, Task 0.5 status

**Date:** 16 November 2026

- Added `compose.yaml` for PostgreSQL 16 with a loopback-only port binding, required local password, health check, and named persistent volume.
- Added PostgreSQL Compose variables to `backend/.env.example` and documented local start/stop commands. The active `HMS_DATABASE_URL` and SQLite database were not changed.
- YAML parsing and structural checks passed. Docker/Docker Compose is not available in this environment, so `docker compose config`, container startup, and container health could not be verified.

**Status:** Incomplete pending Docker-based validation. Do not proceed to Task 0.6 until Task 0.5's Compose configuration has been validated and the service has started successfully.

## Task 0.1 result

The repository architecture has been inspected and documented in this baseline. No application code, schema, runtime configuration, or data was changed for this task.

**Next action:** Finish Phase 0, Task 0.5 by running `docker compose config`, starting PostgreSQL, and checking its health.

**Approval gate:** Awaiting Docker availability and the user's next instruction.
