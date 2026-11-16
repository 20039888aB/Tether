# TETHER

TETHER is being built as a modular-monolith hospital management system for private hospital deployments. The interface follows the supplied desktop-style references: grouped left navigation, contextual actions, compact status indicators, and data-dense searchable tables. Use only synthetic records in the local development database.

## Architecture baseline

- **Frontend:** React + TypeScript + Ant Design.
- **Backend:** Python 3.13 + FastAPI.
- **Primary datastore:** PostgreSQL 16+. It will be the authoritative store for patient, clinical, and financial records.
- **Live updates:** WebSockets/SignalR-style events will be added behind authenticated APIs when a workflow needs them.
- **Caching:** Redis is intentionally not part of the first slice; introduce it only for measured caching or coordination needs.
- **Structure:** Modular monolith, with capability boundaries for identity, patient access, clinical care, inpatient, billing, inventory, workforce, and reporting.

The current development slice includes session-based login, server-side permission checks, login lockout, SuperAdmin RBAC administration, and a persisted patient-registration and OPD-queue workflow. The SQLite development database is active. PostgreSQL migrations are provided but have not been applied or verified. The operational UI is still incomplete outside patient registration and OPD; clinical and financial audit coverage, MFA, and production hardening are not complete. Do not use real patient, staff, or payment data or expose this development system to a network.

## Run the frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Patient registration and the OPD queue are connected to the backend and SQLite development database. Other navigation modules are not yet operational.

## Run the backend

Python 3.12 or newer is required. From the repository root:

```powershell
Set-Location backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`GET /api/v1/health/live` confirms the process is running; `/api/v1/health/ready` checks the configured database. The local `.env` uses SQLite for development; set `HMS_DATABASE_URL` to change it. Authentication uses a random opaque, server-side session cookie (stored as a hash), a readable CSRF cookie/header pair, and Argon2id password hashes. No default credentials or production secrets are provided.

## Database

`backend/migrations/001_core.sql` through `004_system_owner.sql` define the initial identity, RBAC overrides, patient, OPD, audit, and system-owner schemas. They are PostgreSQL migrations and have not been applied or tested against a running PostgreSQL server in this workspace. For SQLite development, `HMS_DATABASE_URL` is set in `backend/.env`; run `.\.venv\Scripts\python.exe -m app.bootstrap_roles` from `backend` to create/update the tables and seed the role catalog. A database with exactly one active SuperAdmin claims that account as owner; if multiple active SuperAdmins already exist, set `HMS_SYSTEM_OWNER_USERNAME` to the intended account for the one-time claim. On a new installation, run `.\.venv\Scripts\python.exe -m app.bootstrap_admin` after seeding to create the first administrator interactively; that account is the system owner. For PostgreSQL later, apply the migrations in order, then seed roles and bootstrap the administrator. Authentication and patient-access APIs are versioned under `/api/v1`.

## User, role, and permission administration

The supplied HMS roles-and-permissions workbook is represented in `backend/app/core/rbac.py`. The seeded catalog contains 33 roles and 410 permissions, including seven action keys per matrix function. Ordinary roles receive only actions defined in their role matrix. `SuperAdmin` and the designated system owner bypass backend permission checks, including for permissions added later. The built-in SuperAdmin role itself is immutable. The unique database owner cannot be deactivated, lose SuperAdmin status, or have account/access settings changed by another administrator. Owner-specific permission overrides are rejected because owner access cannot be narrowed. A SuperAdmin may assign the role to another user. The built-in `System Administrator` can manage user accounts and assign approved non-SuperAdmin roles, but cannot change role or permission policy. Users can hold multiple roles. SuperAdmin-managed individual allow/deny overrides apply after role grants: explicit deny wins over inherited grants, and explicit allow adds access.

For the current SQLite development database, seed or refresh the catalog from `backend` with:

```powershell
.\.venv\Scripts\python.exe -m app.bootstrap_roles
```

Sign in at the frontend and open **Administration & audit** to manage users, assign roles, edit departments, reset passwords, change custom roles and permissions, configure role privileges, set individual permission overrides, or review the audit log. The owner row is marked and cannot be deactivated, demoted, or modified by another account. To recover the owner after a login lockout or lost password, run `.\.venv\Scripts\python.exe -m app.bootstrap_admin --recover-owner` from `backend` on a trusted host; this prompts for a new password, restores the owner role/status, clears lockout, revokes sessions, and writes an audit event. Initial and reset passwords must be at least 14 characters and should be shared through an approved secure channel. Admin password resets also clear lockouts and revoke active sessions. Account deactivation also revokes active sessions.

The Internal Auditor and System Administrator roles can read the audit log; attempts to read it are themselves recorded. Audit events cover authentication, identity/role changes, patient searches and reads, patient registration/updates, and OPD visit creation; the viewer omits audit metadata. Cash collection and refund approval privileges cannot be combined on one role or user. The optional Dietician, Physiotherapist, and Mortuary Officer roles from the supplemental guidance are not seeded because their access scope was not specified.

The first patient-access slice stores basic demographics, generates an opaque TETHER patient number, supports search/update, flags likely duplicate registrations for manual review, and opens a linked queued OPD visit. These fields and duplicate rules are development defaults, not hospital-approved policy. There is no patient merge/history, appointment scheduling, triage, clinical documentation, diagnostics, inpatient, billing, insurance, pharmacy, theatre, procurement, HR, or operational reporting workflow yet. Permission entries for those modules do not mean the modules are implemented. The supplied workbook and supplemental guidance are planning material, not legal, clinical, or regulatory approval. Do not use real records or payments; confirm data fields, access policy, retention, privacy, and clinical governance before any real-data pilot. PostgreSQL migration and deployment remain deferred.

## Development sequence

1. Foundation: identity, permission enforcement, audit pipeline, and application shell (development implementation present; production hardening remains).
2. Patient registration, duplicate review, and persisted OPD queue (initial SQLite-backed slice present; appointments, patient merge/history, and clinical queue transitions remain).
3. Clinical encounters, nursing, diagnostics, and results.
4. Billing, payments, receipts, corrections, approvals, and reconciliation.
5. Admissions, wards, bed allocation, transfers, and discharge.
6. Pharmacy, inventory, procurement, and stock audit.
7. Accounting, workforce, insurance, and reporting.
8. External integrations, security testing, recovery drills, and deployment hardening.

Before any real deployment, complete threat modeling, applicable Kenyan legal/privacy review, role and permission design, encrypted backup/restore drills, infrastructure hardening, and independent security testing.
