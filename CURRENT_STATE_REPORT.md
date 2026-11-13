# CareGrid HMS — Current State and Improvement Report

**Assessment date:** 13 November 2026  
**Repository:** [20039888aB/Tether](https://github.com/20039888aB/Tether)  
**Branch and revision assessed:** `main` at `9bfe5d8483215e381fa6b3e695b6ed911637b418`  
**Overall maturity:** Early development foundation / demonstrator — **not a hospital-ready system**

## Executive summary

The repository is a greenfield starter with a useful first visual prototype and the start of an API foundation. The frontend captures several recognizable elements of the supplied references—grouped navigation, dense operational tables, queue statuses, summary cards, search, filters, and pagination. The backend has initial account/session models, login and permission-checking routes, health checks, a PostgreSQL schema, and an administrator-bootstrap script.

The current frontend queue is sample data held in the browser. The frontend does not authenticate against the API, read or write persistent records, or receive real-time events. The SQL migration has not been applied to PostgreSQL in this workspace. There are no patient registration, clinical, admissions, billing, payment, pharmacy, accounting, or HR workflows behind the navigation.

**Conclusion:** This is a credible prototype foundation, but it is not safe or complete for clinical use, financial processing, real patient data, or production/on-premises deployment. Prioritize a verified database setup and secure, authenticated end-to-end patient-registration slice before adding broad module coverage.

## Evidence and scope

This assessment is based on the checked-out project files, the latest frontend build and lint, the backend test and lint runs, and the known workspace capability to run a production frontend build. The current branch was clean at the assessed revision.

Verification performed:

- Backend: **5 tests passed**; Ruff lint passed.
- Frontend: TypeScript/Vite production build passed; oxlint passed.
- The frontend build emits a **large JavaScript bundle warning** (about 972 kB uncompressed, 306 kB gzip).
- The test environment emits one Starlette/AnyIO deprecation warning.
- PostgreSQL migration execution and live database readiness were **not** verified. PostgreSQL client/server tools were not available during this assessment.

This is a current-state engineering assessment, not an independent penetration test, code certification, clinical safety review, performance benchmark, legal opinion, or compliance attestation.

## Current implementation

| Area | Present now | Not yet present / limitation |
|---|---|---|
| Frontend | React + TypeScript + Ant Design shell; collapsible grouped navigation; synthetic patient-queue rows; status badges, search/status filter, sorting, and table pagination; responsive sidebar behavior. | No login screen or authenticated API client. Navigation selections mostly change the page heading rather than render functional modules. Queue metrics, status, and data are hard-coded; no real calendar, registration form, patient profile, or live queue. |
| API | FastAPI application; OpenAPI in development; liveness and readiness endpoints; versioned auth routes. | No patient or clinical endpoints, API integration with the frontend, production hosting configuration, application-wide rate limiting, or durable event/notification delivery. |
| Authentication | Argon2 password verification; opaque random server-side sessions; hashed session and CSRF tokens; HttpOnly session cookie; CSRF validation for protected state-changing actions; account lockout counter; generic login error; login/session audit attempts. | No MFA, identity-provider/OIDC integration, password reset/change, account-management API, session-management UI, configurable password policy, or comprehensive abuse controls. |
| Authorization | Role/permission tables; permission guard on the sample user-list API; seeded role permissions in SQL. | No facility/department/patient-context ABAC, permission-aware frontend, role administration interface/API, broad authorization tests, or review of the final clinical and finance permission matrix. UI hiding is not authorization. |
| Database | PostgreSQL-oriented SQL migration for roles, permissions, users, sessions, and audit logs. SQLAlchemy models can support SQLite-based tests. | Migration is not part of a migration-runner/version table workflow; no PostgreSQL instance or migration verification; no database deployment, backups, restore drills, data retention, or operational monitoring. |
| Audit | Audit table, indexes, application-level identity/session audit events, and a database trigger rejecting audit-row update/delete. | Audit covers only identity-related routes, not patient record access, exports, clinical activity, financial actions, system administration, or integrations. No append-only database-role design, tamper-evident external copy, audit viewer, or retention policy. |
| Integrations/realtime | Product direction is documented. | No SMS/voice, mobile-money/payment, insurance, lab, FHIR/DICOM, event bus, WebSocket, webhook, retry, or reconciliation implementation. |
| Deployment | Development setup notes and an environment example. | No Dockerfile, Compose stack, TLS termination, secrets/key management, supported deployment/upgrade sequence, monitoring, recovery plan, or production runbook. |

## Important safety and security gaps

1. **The UI currently exposes demo records without authentication.** They are synthetic, but the eventual patient-facing views must require authenticated server authorization. Do not populate this UI with real data.
2. **There is no medical-record access-control model.** A role name alone is not enough; patient context, facility/department scope, care relationship, purpose, and emergency access rules may need to affect authorization.
3. **Account lockout is not a complete abuse defense.** Per-account limits can be abused to deny service to a known user, and there is no centralized IP/device rate limiting, alerting, MFA, or account recovery flow.
4. **No production-grade identity policy is established.** Session rotation/limits, revocation of all active sessions, idle timeout, MFA for privileged access, password changes, secure recovery, and deployment cookie/proxy behavior need definition and tests.
5. **The audit claim must stay narrow.** The schema blocks updates and deletes with a trigger, but database owners can change schema or bypass ordinary application controls. It does not independently prove immutability or detect privileged tampering.
6. **Production operational security is missing.** Encryption at rest/backups, key ownership and rotation, TLS, firewall/network segmentation, patch/vulnerability management, monitoring, least-privilege database credentials, backups, and tested restoration are not implemented or verified.
7. **No local legal/privacy assessment has been completed.** Obtain qualified review for Kenyan health data, privacy, retention, consent, patient rights, and external data processing before real deployment.
8. **Payment and clinical safety controls do not yet exist.** Do not handle real payments, prescriptions, care decisions, or treatment documentation with this starter.

## Prioritized improvement roadmap

### P0 — Make the foundation reproducible and verifiable

- Add a pinned, supported PostgreSQL development service (typically via Docker Compose), explicit health checks, and documented non-production credentials loaded only from local environment files.
- Adopt a migration runner (for example Alembic) and establish a migration-version table, upgrade ordering, failure handling, and schema smoke test. Verify the initial schema on PostgreSQL, not just SQLite.
- Add backend and frontend CI for install, lint, unit/integration tests, type/build, and migration checks. Add dependency lock/update and vulnerability scanning.
- Add API validation/error conventions, structured logs with correlation IDs and PHI/secret redaction, request size/time limits, and production-safe configuration validation.
- Fix the large frontend bundle by analyzing its dependency composition and applying evidence-based code splitting/tree-shaking; set an agreed bundle budget.
- Define deployment/runbook prerequisites and confirm frontend/API origin, TLS termination, trusted-proxy settings, CORS, cookies, and secrets management.

**Acceptance gate:** a clean checkout can start the database, apply migrations, run the API and frontend, and pass automated checks with no real secrets or real patient data.

### P1 — Complete secure identity and permission foundation

- Decide and document the identity/session threat model, MFA policy, session lifetimes, account recovery, privileged-user controls, and emergency access approach.
- Add administrator-controlled user/role/permission management with last-admin protections and audit coverage. Never use public signup or default credentials.
- Add database-backed, configurable rate limiting and monitoring for login attempts; assess lockout denial-of-service trade-offs.
- Test unauthorized, expired, revoked, inactive, cross-role, CSRF, account-lock, and permission-change scenarios; verify sensitive actions are audited.
- Add API client authentication to the frontend, logout, session-expiry handling, an access-denied state, and permission-aware navigation as a UX layer. Server checks remain authoritative.
- Extend audit coverage to successful/denied access of sensitive records, exports, administrative changes, and later clinical and financial events. Define audit access, retention, external forwarding, and tamper response.

**Acceptance gate:** documented role/permission matrix and automated evidence that every protected sample API denies unauthorized requests; authentication flows work end-to-end in the UI.

### P2 — Build the first real vertical slice: reception and patient access

- Confirm patient registration fields, locally required identifiers, consent, demographics, contact/next-of-kin details, payer model, duplicate-resolution policy, and access scope with clinical/operations stakeholders.
- Model patient, contact/next-of-kin, consent, payer/coverage, visit, appointment, clinic, and queue state with constraints and indexed search; define patient-number generation and merge history.
- Implement patient search, registration, duplicate review, view/edit permissions, appointment/check-in, and auditable queue transitions through versioned APIs and PostgreSQL transactions.
- Define allowed queue transitions server-side and record the actor/time/reason; add synthetic-data fixtures only.
- Connect the UI to the API, add form validation and clear loading/error/empty states, and verify keyboard/accessible behavior.
- Add duplicate, validation, authorization, concurrency, pagination, sorting/filter, audit, and end-to-end tests.

**Acceptance gate:** a receptionist can register a synthetic patient, find/review a possible duplicate, create/check in a visit, and move it through an approved queue transition with correct permissions and audit events.

### P3 — Establish clinical safety before clinical features

- Have qualified clinical stakeholders define encounter structure, terminology, authorship, versioning, signing, amendments, allergies, medication reconciliation, vitals, orders, results, and emergency/ downtime workflows.
- Protect signed entries from silent edits. Record amendments and preserve provenance.
- Scope nurse and doctor worklists, results routing, clinical note visibility, consent, and record access at the patient and care-team level.
- Evaluate HL7 FHIR and, where required, DICOM/DICOMweb against the actual partner interfaces and local requirements.
- Perform clinical workflow hazard analysis and usability testing before piloting with any real clinical users or records.

### P4 — Implement inpatient and diagnostics workflows

- Add laboratory/radiology orders, specimen lifecycle, result verification, critical-result escalation, attachments, and audit controls.
- Add wards, rooms, beds, capacity/cleaning/maintenance statuses, admissions approval, transfers, discharge, and bed history.
- Prevent double-booking and invalid state transitions using database constraints/transactions and concurrency tests.
- Define downtime, queue reconciliation, and notification handling when realtime connections fail.

### P5 — Implement billing with financial controls

- Model immutable posted invoices and lines, payer allocation, deposits, payment attempts, receipts, reversals, refunds, and reconciliation.
- Use an approval workflow and separation of duties for invoice correction/void, refunds, cash disbursement, and accounting posting.
- Integrate payment processors only through documented adapters with provider verification, idempotency, webhook replay protection, reconciliation, and no card-data storage.
- Implement accounting ledgers as balanced, traceable transactions; align accounting periods, currency, rounding, taxes, and insurance claims with stakeholders and current local rules.
- Load-test and test duplicate callbacks, partial payment, reversal, timeout, and settlement discrepancies before real transactions.

### P6 — Inventory, workforce, reporting, and communications

- Add medicine/product catalog, batch/expiry/stock movements, dispensing, suppliers, purchasing, stock counts, and reorder controls.
- Add HR/staff/roster boundaries and tightly scoped roles.
- Add permission-aware operational reports and export audit/limits.
- Integrate SMS/voice only after consent, opt-out, sensitive-message content, delivery retries, provider secrets, and data-processing arrangements are agreed.
- Add insurer/SHA and other partner adapters only against current documented contracts/test environments and verified API specifications.

### P7 — Production readiness and controlled rollout

- Complete a threat model, independent security review, secure configuration review, dependency/container scans, and penetration test.
- Establish hardened on-prem infrastructure: private subnets, network firewalls, managed TLS, least privilege, OS/database patching, admin VPN, monitoring/alerting, and protected secrets/keys.
- Encrypt database volumes and backups with documented independent key custody/rotation. Test restore, ransomware recovery, offline/immutable copies, RPO/RTO, and business continuity.
- Define upgrades, rollback/forward-only migrations, monitoring, incident response, access reviews, and support ownership.
- Conduct load/performance testing on representative synthetic datasets and realistic concurrency before procurement of production capacity.
- Pilot using synthetic/de-identified data first; release to real operations only after qualified clinical, security, legal, privacy, and operational sign-off.

## Architecture and product decisions still required

1. Confirm whether each hospital gets a completely isolated installation/database, or whether any central service is allowed for license management, updates, or support telemetry.
2. Select the hospital’s identity model: local accounts with MFA, an existing OIDC identity provider, or both. Specify break-glass and offline operation.
3. Define facility/department/patient-level permissions and which roles may create, read, amend, sign, approve, export, or delete each record type.
4. Confirm which workflows are in the first operational pilot: outpatient reception, appointments, triage, a specific clinical service, or admissions.
5. Confirm Kenyan identifiers, consent and privacy workflows, payer/insurance requirements, KES accounting rules, and the payment/SMS providers that have approved sandbox access.
6. Identify existing hospital software and data sources, migration ownership, data quality, interoperability standards, and cutover/rollback expectations.
7. Establish target user/concurrent-user counts, peak registrations/queue updates, uptime goals, support coverage, internet dependence, and recovery objectives.

## Recommended immediate next milestone

Complete **P0 foundation**, then implement **P1 identity with UI integration**, followed by the **P2 reception/patient registration vertical slice**. Do not start payments, clinical notes, real messaging, or production data until their distinct safety, privacy, audit, and operational controls have been designed and verified.

## Project links

- [Project setup and architecture notes](./README.md)
- [Authentication endpoints](./backend/app/api/auth.py)
- [Core PostgreSQL migration](./backend/migrations/001_core.sql)
- [Backend tests](./backend/tests)
- [Frontend shell and synthetic queue](./frontend/src/App.tsx)
