ALTER TABLE users
    ADD COLUMN totp_secret_encrypted bytea,
    ADD COLUMN totp_pending_secret_encrypted bytea,
    ADD COLUMN totp_enabled_at timestamptz;
