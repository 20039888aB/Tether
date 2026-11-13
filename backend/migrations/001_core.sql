CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_key text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT ''
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    failed_login_attempts integer NOT NULL DEFAULT 0 CHECK (failed_login_attempts >= 0),
    locked_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    granted_at timestamptz NOT NULL DEFAULT now(),
    granted_by uuid REFERENCES users(id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permissions (
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    csrf_token_hash bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);

CREATE INDEX auth_sessions_user_active_idx
    ON auth_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
    source_ip text,
    user_agent text,
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX audit_logs_occurred_at_idx ON audit_logs (occurred_at DESC);
CREATE INDEX audit_logs_actor_occurred_at_idx ON audit_logs (actor_user_id, occurred_at DESC);
CREATE INDEX audit_logs_resource_idx ON audit_logs (resource_type, resource_id);

CREATE FUNCTION reject_audit_log_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$;

CREATE TRIGGER audit_logs_no_update
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();

INSERT INTO roles (name, description) VALUES
    ('SuperAdmin', 'Hospital-wide system administration'),
    ('Admin', 'Hospital administration'),
    ('Doctor', 'Clinical doctor workflows'),
    ('Nurse', 'Nursing workflows'),
    ('Receptionist', 'Patient access workflows'),
    ('Cashier', 'Payment collection workflows'),
    ('Accountant', 'Restricted accounting workflows'),
    ('LabTech', 'Laboratory workflows'),
    ('Pharmacist', 'Pharmacy workflows'),
    ('HRManager', 'Human resources workflows');

INSERT INTO permissions (permission_key, description) VALUES
    ('identity.users.read', 'Read user accounts'),
    ('identity.users.manage', 'Create, update, and disable user accounts'),
    ('identity.roles.manage', 'Manage roles and permission assignments'),
    ('audit.read', 'Read security and audit events'),
    ('patients.read', 'Read patient access records'),
    ('patients.create', 'Register patients'),
    ('patients.update', 'Update patient demographic records'),
    ('clinical.read', 'Read authorized clinical records'),
    ('clinical.write', 'Create and amend clinical records'),
    ('billing.read', 'Read billing records'),
    ('billing.manage', 'Manage invoices and payment workflows'),
    ('accounting.read', 'Read accounting records'),
    ('accounting.manage', 'Manage accounting workflows'),
    ('appointments.read', 'Read appointment schedules'),
    ('appointments.manage', 'Manage appointment schedules'),
    ('admissions.manage', 'Manage admission workflows'),
    ('laboratory.read', 'Read laboratory orders and results'),
    ('laboratory.write', 'Record laboratory results'),
    ('pharmacy.dispense', 'Dispense prescribed medication'),
    ('wards.manage', 'Manage ward, room, and bed workflows'),
    ('inventory.read', 'Read pharmacy and inventory records'),
    ('inventory.manage', 'Manage pharmacy and inventory workflows'),
    ('workforce.manage', 'Manage staff and roster workflows'),
    ('reports.read', 'Read authorized operational reports');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'SuperAdmin';

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'Accountant'
  AND permissions.permission_key IN ('accounting.read', 'accounting.manage');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'Admin'
  AND permissions.permission_key IN (
      'identity.users.read',
      'identity.users.manage',
      'identity.roles.manage',
      'audit.read',
      'accounting.read',
      'accounting.manage',
      'reports.read'
  );

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name IN ('Doctor', 'Nurse')
  AND permissions.permission_key IN ('patients.read', 'clinical.read', 'clinical.write');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'Receptionist'
  AND permissions.permission_key IN (
      'patients.read',
      'patients.create',
      'patients.update',
      'appointments.read',
      'appointments.manage'
  );

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'Cashier'
  AND permissions.permission_key IN ('billing.read', 'billing.manage');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'LabTech'
  AND permissions.permission_key IN ('patients.read', 'laboratory.read', 'laboratory.write');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'Pharmacist'
  AND permissions.permission_key IN ('inventory.read', 'pharmacy.dispense');

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.name = 'HRManager' AND permissions.permission_key = 'workforce.manage';
