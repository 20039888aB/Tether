# TETHER — Current State and Improvement Report

**Assessment date:** 16 November 2026
**Repository:** [20039888aB/Tether](https://github.com/20039888aB/Tether)  
**Branch and revision assessed:** `main` at `14eaff8f129831d86a88326519fa6c75bc8b92dc`
**Overall maturity:** Early development foundation / demonstrator — **not a hospital-ready system**

## Executive summary

The repository is an early development system with an identity/authorization foundation and one persisted operational slice. The frontend authenticates against the API, filters navigation by permission, provides SuperAdmin role/permission and user administration with an audit viewer, and connects patient registration and the OPD queue to the backend.

The patient and OPD slice supports synthetic patient registration, search, update, likely-duplicate rejection, and persistent queued visits. Other navigation modules remain placeholders; there are no clinical, admissions, billing, payment, pharmacy, accounting, or HR workflows. SQLite is the development database; PostgreSQL migrations have not been applied or verified.

**Conclusion:** This is not a hospital-ready system. Do not use it for clinical care, financial processing, real patient data, or production deployment. Continue with stakeholder-reviewed workflows, production database migrations, and security/privacy hardening before expanding module coverage.

## Evidence and scope

This assessment is based on the checked-out project files, frontend build and lint, backend tests and lint, SQLite role seeding, and direct API/CORS health checks. The worktree contains uncommitted changes; the new patient screens have not been browser-verified.

Verification performed:

- Backend: **19 tests passed**; Ruff lint passed.
- Frontend: TypeScript/Vite production build passed; oxlint completed with four React set-state-in-effect warnings.
- The frontend build emits a **large JavaScript bundle warning** (about 1.05 MB uncompressed, 328 kB gzip).
- The test environment emits one Starlette/AnyIO deprecation warning.
- SQLite seeding created 33 roles and 410 catalog permissions.
- SQLite migration marked the sole active SuperAdmin as the designated system owner and created a unique owner index.
- Both development servers responded successfully; readiness and CORS checks passed. After refreshing, the shared browser displayed the patient queue and registration form without a fetch error.
- PostgreSQL migration execution and readiness were **not** verified.

This is a current-state engineering assessment, not an independent penetration test, code certification, clinical safety review, performance benchmark, legal opinion, or compliance attestation.

## Current implementation

| Area | Present now | Not yet present / limitation |
|---|---|---|
| Frontend | React + TypeScript + Ant Design; authenticated login/logout; permission-filtered navigation; owner-protected SuperAdmin/user/role/permission administration; audit viewer; patient registration/search/edit and queued OPD visit screens. | Clinical, admissions, diagnostics, billing, pharmacy, accounting, inventory, HR, reports, and real-time events remain placeholders. Registration and OPD screens loaded in the browser; end-to-end create/edit flows have not been browser-exercised. |
| API | FastAPI; liveness/readiness; versioned identity and patient-access routes; server-side permission guards; patient search/registration/update; OPD visit creation/queue reads. | No clinical endpoints, application-wide rate limiting, appointment scheduling, queue transitions, or durable event/notification delivery. |
| Authentication | Argon2 verification; opaque random server-side sessions; hashed session and CSRF tokens; HttpOnly session cookie; CSRF validation; account lockout; audited password resets and session revocation. The designated system owner is stored in the database, has backend SuperAdmin bypass, and cannot be deactivated or demoted through application APIs. A trusted-host CLI recovery resets the owner password/lockout and revokes sessions. | No MFA, identity-provider/OIDC integration, web-based self-service recovery, session-management UI, or comprehensive abuse controls. Temporary login lockout still applies until the owner uses the local recovery command. |
| Authorization | 33 seeded roles; 410 catalog permissions; server-side identity and patient-access guards; SuperAdmin role/permission CRUD and individual allow/deny overrides; deny-over-role precedence; cashier/refund-approver separation. Owner access is immutable and independent of role permission rows. | No facility/department/patient-context ABAC. Most operational permissions remain catalog entries with no domain API. Additional separation-of-duties policies require local approval. |
| Database | SQLite development database configured and seeded; SQLAlchemy patient, OPD, identity, and audit models. | PostgreSQL migrations are not part of a verified migration-runner workflow; no PostgreSQL deployment, backups, restore drills, data retention, or operational monitoring. |
| Audit | Authentication, identity/role/permission administration, patient search/read/register/update, and OPD visit creation are audited; audit reads are logged. The PostgreSQL initial migration defines an audit mutation-rejecting trigger. | No clinical/financial audit events, external tamper-evident copy, retention policy, or equivalent verified SQLite immutability trigger. |
| Integrations/realtime | Product direction is documented. | No SMS/voice, mobile-money/payment, insurance, lab, FHIR/DICOM, event bus, WebSocket, webhook, retry, or reconciliation implementation. |
| Deployment | Development setup notes and an environment example. | No Dockerfile, Compose stack, TLS termination, secrets/key management, supported deployment/upgrade sequence, monitoring, recovery plan, or production runbook. |

## Important safety and security gaps

1. **The patient workflow is a limited development slice.** It stores basic demographics and queued OPD visits, but has no patient merge/history, appointments, triage, clinical documentation, or approved real-world registration policy. Use synthetic data only.
2. **There is no medical-record access-control model.** A role name alone is not enough; patient context, facility/department scope, care relationship, purpose, and emergency access rules may need to affect authorization.
3. **Account lockout is not a complete abuse defense.** Per-account limits can be abused to deny service to a known user, and there is no centralized IP/device rate limiting, alerting, MFA, or account recovery flow.
4. **No production-grade identity policy is established.** Session limits, idle timeout, MFA for privileged access, self-service recovery, and deployment cookie/proxy behavior need definition and tests. Admin password resets are not a complete account-recovery flow.
5. **The audit claim must stay narrow.** Identity and the initial patient-access slice are audited, but there are no clinical/financial events. The PostgreSQL schema trigger is not an external tamper-evident copy and does not detect privileged tampering; SQLite immutability is not verified.
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
- Last-active-SuperAdmin protection and SuperAdmin-only policy changes are implemented. Add secure self-service recovery/password change, confirmation for high-impact actions, and additional privileged-account safeguards.
- Add database-backed, configurable rate limiting and monitoring for login attempts; assess lockout denial-of-service trade-offs.
- Expand tests for expired sessions, concurrency, and policy edge cases; existing coverage includes permission overrides, CSRF, lockout, password reset/session revocation, audit access, last-SuperAdmin protection, role changes, and separation of duties.
- Add session-expiry handling and an access-denied state. Frontend login/logout and permission-aware navigation exist as UX layers; server checks remain authoritative.
- Extend audit coverage to sensitive-record access, exports, and future clinical/financial events. Define retention, external forwarding, and tamper response.

**Acceptance gate:** documented role/permission matrix and automated evidence that every protected sample API denies unauthorized requests; authentication flows work end-to-end in the UI.

### P2 — Complete the reception and patient-access slice

- Confirm patient registration fields, locally required identifiers, consent, demographics, contact/next-of-kin details, payer model, duplicate-resolution policy, and access scope with clinical/operations stakeholders.
- The current SQLite slice models basic patient demographics and linked queued visits, uses generated patient/visit identifiers, and audits patient access and changes. Extend only after stakeholders approve fields and duplicate policy.
- Implement patient merge/history, contact/next-of-kin, consent, payer/coverage, appointment scheduling, check-in, and auditable queue transitions through versioned APIs and verified PostgreSQL transactions.
- Define allowed queue transitions server-side and record the actor/time/reason; add synthetic-data fixtures only.
- Connect remaining workflow screens to the API; the initial registration/search/edit and queue screens now have loading/error/empty states but need browser/accessibility verification.
- Add concurrency, patient-merge, transition, pagination, and broader end-to-end tests; current backend tests cover registration, duplicate conflict, update, queue linkage, audit, and unauthorized access.

**Acceptance gate:** a receptionist can register and find synthetic patients, resolve duplicates through an approved review process, and move visits through stakeholder-approved queue transitions with correct permissions and audit events.

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

Complete remaining **P1 identity hardening** and browser-verify the **P2 patient registration/OPD slice**. Then stage the remaining modules with clinical, privacy, security, and operational review. Do not use production patient data, payments, clinical notes, or messaging until their distinct safety, privacy, audit, and operational controls have been designed and verified.

## Project links

- [Project setup and architecture notes](./README.md)
- [Authentication endpoints](./backend/app/api/auth.py)
- [Core PostgreSQL migration](./backend/migrations/001_core.sql)
- [Backend tests](./backend/tests)
- [Frontend shell and patient access screens](./frontend/src/App.tsx)
