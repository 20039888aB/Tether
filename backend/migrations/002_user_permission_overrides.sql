ALTER TABLE users
    ADD COLUMN department varchar(128);

CREATE TABLE user_permission_overrides (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    is_granted boolean NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, permission_id)
);

CREATE INDEX user_permission_overrides_updated_by_idx
    ON user_permission_overrides (updated_by, updated_at DESC);
