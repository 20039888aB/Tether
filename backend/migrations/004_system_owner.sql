ALTER TABLE users
    ADD COLUMN is_system_owner boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX uq_users_system_owner
    ON users (is_system_owner)
    WHERE is_system_owner;
