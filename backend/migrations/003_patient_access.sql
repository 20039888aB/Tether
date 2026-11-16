CREATE TABLE patients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_number varchar(40) NOT NULL UNIQUE,
    first_name varchar(100) NOT NULL,
    middle_name varchar(100),
    last_name varchar(100) NOT NULL,
    date_of_birth date,
    sex_at_birth varchar(16),
    phone_number varchar(32),
    email varchar(320),
    address varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    CHECK (sex_at_birth IS NULL OR sex_at_birth IN ('female', 'male', 'intersex', 'unknown'))
);

CREATE INDEX patients_last_name_idx ON patients (last_name);
CREATE INDEX patients_phone_number_idx ON patients (phone_number);

CREATE TABLE outpatient_visits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id uuid NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
    visit_number varchar(40) NOT NULL UNIQUE,
    clinic varchar(128) NOT NULL,
    visit_type varchar(64) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    CHECK (status IN ('queued', 'cancelled', 'completed'))
);

CREATE INDEX outpatient_visits_patient_created_idx
    ON outpatient_visits (patient_id, created_at DESC);
CREATE INDEX outpatient_visits_status_created_idx
    ON outpatient_visits (status, created_at DESC);
