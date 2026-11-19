ALTER TABLE patients
    ADD COLUMN next_of_kin_name varchar(200),
    ADD COLUMN next_of_kin_phone varchar(32),
    ADD COLUMN next_of_kin_relationship varchar(32),
    ADD COLUMN next_of_kin_relationship_other varchar(100),
    ADD CONSTRAINT patients_next_of_kin_complete_check CHECK (
        (next_of_kin_name IS NULL AND next_of_kin_phone IS NULL
            AND next_of_kin_relationship IS NULL)
        OR
        (next_of_kin_name IS NOT NULL AND next_of_kin_phone IS NOT NULL
            AND next_of_kin_relationship IS NOT NULL)
    ),
    ADD CONSTRAINT patients_next_of_kin_relationship_check CHECK (
        next_of_kin_relationship IS NULL OR next_of_kin_relationship IN (
            'spouse', 'partner', 'parent', 'mother', 'father', 'child', 'son',
            'daughter', 'sibling', 'brother', 'sister', 'grandparent',
            'grandmother', 'grandfather', 'grandchild', 'aunt', 'uncle',
            'niece', 'nephew', 'cousin', 'step_parent', 'step_child',
            'parent_in_law', 'child_in_law', 'sibling_in_law', 'guardian',
            'legal_guardian', 'foster_parent', 'caregiver', 'friend',
            'neighbor', 'other'
        )
    ),
    ADD CONSTRAINT patients_next_of_kin_other_check CHECK (
        (next_of_kin_relationship = 'other'
            AND next_of_kin_relationship_other IS NOT NULL)
        OR (next_of_kin_relationship IS NULL
            AND next_of_kin_relationship_other IS NULL)
        OR (next_of_kin_relationship IS NOT NULL
            AND next_of_kin_relationship != 'other'
            AND next_of_kin_relationship_other IS NULL)
    );

ALTER TABLE outpatient_visits
    ADD COLUMN workflow_state varchar(32) NOT NULL DEFAULT 'awaiting_triage';

UPDATE outpatient_visits
SET workflow_state = CASE status
    WHEN 'completed' THEN 'completed'
    WHEN 'cancelled' THEN 'cancelled'
    ELSE 'awaiting_triage'
END;

ALTER TABLE outpatient_visits
    ADD CONSTRAINT outpatient_visits_workflow_state_check CHECK (
        workflow_state IN (
            'awaiting_triage', 'awaiting_doctor', 'consultation_in_progress',
            'completed', 'cancelled'
        )
    );

CREATE TABLE visit_triages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_id uuid NOT NULL UNIQUE REFERENCES outpatient_visits(id) ON DELETE RESTRICT,
    blood_pressure_systolic integer,
    blood_pressure_diastolic integer,
    pulse_rate_bpm integer,
    temperature_celsius double precision,
    respiratory_rate_bpm integer,
    oxygen_saturation_percent integer,
    weight_kg double precision,
    height_cm double precision,
    pain_score integer,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES users(id) ON DELETE RESTRICT,
    CHECK (
        blood_pressure_systolic IS NULL OR blood_pressure_diastolic IS NULL
        OR blood_pressure_systolic > blood_pressure_diastolic
    )
);

CREATE TABLE consultation_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_id uuid NOT NULL REFERENCES outpatient_visits(id) ON DELETE RESTRICT,
    parent_note_id uuid REFERENCES consultation_notes(id) ON DELETE RESTRICT,
    note_type varchar(16) NOT NULL DEFAULT 'consultation',
    body text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'draft',
    author_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    signed_at timestamptz,
    CHECK (status IN ('draft', 'signed')),
    CHECK (note_type IN ('consultation', 'addendum')),
    CHECK (
        (note_type = 'consultation' AND parent_note_id IS NULL)
        OR (note_type = 'addendum' AND parent_note_id IS NOT NULL)
    )
);

CREATE INDEX consultation_notes_visit_id_idx ON consultation_notes (visit_id);
CREATE INDEX consultation_notes_author_user_id_idx ON consultation_notes (author_user_id);
CREATE INDEX consultation_notes_visit_created_idx
    ON consultation_notes (visit_id, created_at);
