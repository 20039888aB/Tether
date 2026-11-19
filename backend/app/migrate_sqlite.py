import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import Base
from app.db.session import get_engine

MIGRATION_VERSIONS = (
    "001_core",
    "002_user_permission_overrides",
    "003_patient_access",
    "004_system_owner",
    "005_mfa_totp",
    "006_patient_clinical_workflow",
    "007_system_change_events",
    "008_clinic_management",
)

CLINIC_CATALOG = (
    ("OPD", "OUT PATIENT (OPD)", 1),
    ("DENTAL", "DENTAL", 2),
    ("EYE", "EYE", 3),
    ("PDENT", "PEADIATRIC DENTIST", 4),
    ("ENDO", "ENDOSCOPY AND LAPARASCOPIC SURGERY", 5),
    ("DERM", "DERMATOLOGY", 6),
    ("PSURG", "PEADIATRIC SURGERY", 7),
    ("PHYSIO", "PHYSIOTHERAPY", 8),
    ("MOPC", "MEDICAL OUTPATIENT CLINIC (MOPC)", 9),
    ("NEUROSURG", "NEUROSURGERY", 10),
    ("POPC", "PAEDIATRIC OUTPATIENT CLINIC (POPC)", 11),
    ("ANC", "ANC CLINIC", 12),
    ("OBGLAP", "OBS/GYNAE (LAPARASCOPY)", 13),
    ("SOPC", "SURGICAL OUTPATIENT CLINIC (SOPC)", 14),
    ("PLASTIC", "PLASTIC SURGERY", 15),
    ("OBGYN", "OBS/GYNAECOLOGY CLINIC", 16),
    ("ENT", "EAR, NOSE AND THROAT (ENT)", 17),
    ("URO", "UROLOGY CLINIC", 18),
    ("PSYCH", "PSYCOLOGY & PSYCHIATRIST CLINICS", 19),
    ("SPEECH", "SPEECH THERAPY", 20),
    ("SPINE", "SPINE SURGERY", 21),
    ("MCH", "MCH", 22),
    ("IR", "INTERVENTIONAL RADIOLOGY", 23),
    ("MAXFAC", "MAXILLOFACIAL", 24),
    ("CWC", "CHILD WELFARE CLINIC (CWC)", 25),
    ("CASUALTY", "CASUALTY", 26),
    ("NUTRI", "NUTRITION", 27),
    ("EYESURG", "EYE SURGERY AND OPTHAMOLOGY CLINICS", 28),
    ("ORTHODONT", "ORTHODONTIST CLINICS", 29),
    ("HIGHRISK", "HIGH RISK", 30),
    ("ORTHO", "ORTHOPAEDIC", 31),
    ("COUNSEL", "COUNSELLING", 32),
    ("FP", "FAMILY PLANNING", 33),
    ("PNC", "POSTNATAL CARE", 34),
    ("ANTENATAL", "ANTENATAL CARE", 35),
)


async def _seed_clinic_catalog(connection) -> None:
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO facilities (id, name, is_active) "
        "VALUES (1, 'TETHER Development Facility', 1)"
    )
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO visit_types (name, color_hex, is_active) VALUES "
        "('SICK', '#F26B6B', 1), "
        "('MATERNAL AND CHILD HEALTH CARE', '#2C9BE8', 1), "
        "('1ST ANC VISIT (0-12 WEEKS)', '#2C9BE8', 1)"
    )
    for code, name, sort_order in CLINIC_CATALOG:
        await connection.execute(
            text(
                "INSERT OR IGNORE INTO clinics (code, name, sort_order, is_deleted) "
                "VALUES (:code, :name, :sort_order, 0)"
            ),
            {"code": code, "name": name, "sort_order": sort_order},
        )
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO clinic_visit_types (clinic_id, visit_type_id) "
        "SELECT c.id, v.id FROM clinics c CROSS JOIN visit_types v "
        "WHERE c.code NOT IN ('ANC', 'ANTENATAL') AND v.name = 'SICK'"
    )
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO clinic_visit_types (clinic_id, visit_type_id) "
        "SELECT c.id, v.id FROM clinics c CROSS JOIN visit_types v "
        "WHERE c.code = 'ANC' AND v.name = 'MATERNAL AND CHILD HEALTH CARE'"
    )
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO clinic_visit_types (clinic_id, visit_type_id) "
        "SELECT c.id, v.id FROM clinics c CROSS JOIN visit_types v "
        "WHERE c.code = 'ANTENATAL' AND v.name = '1ST ANC VISIT (0-12 WEEKS)'"
    )
    await connection.exec_driver_sql(
        "INSERT OR IGNORE INTO facility_clinics (facility_id, clinic_id, is_enabled) "
        "SELECT 1, id, 1 FROM clinics WHERE is_deleted = 0"
    )
    existing_numbers = (
        await connection.execute(text("SELECT patient_number FROM patients"))
    ).scalars().all()
    last_number = max(
        [
            11313,
            *(
                int(patient_number[4:])
                for patient_number in existing_numbers
                if patient_number.startswith("TTH-") and patient_number[4:].isdigit()
            ),
        ]
    )
    await connection.execute(
        text(
            "INSERT INTO patient_number_counters (id, value) VALUES (1, :value) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"value": last_number},
    )
    await connection.exec_driver_sql(
        "UPDATE users SET facility_id = 1 "
        "WHERE facility_id IS NULL AND is_system_owner = 0 "
        "AND id NOT IN ("
        "SELECT ur.user_id FROM user_roles ur "
        "JOIN roles r ON r.id = ur.role_id WHERE r.name = 'SuperAdmin'"
        ")"
    )


async def _rebuild_system_events_category_check(connection) -> None:
    await connection.exec_driver_sql("DROP TRIGGER IF EXISTS system_events_no_update")
    await connection.exec_driver_sql("DROP TRIGGER IF EXISTS system_events_no_delete")
    await connection.exec_driver_sql("DROP INDEX IF EXISTS system_events_category_id_idx")
    await connection.exec_driver_sql(
        "ALTER TABLE system_events RENAME TO system_events_before_clinic_management"
    )
    await connection.exec_driver_sql(
        "CREATE TABLE system_events ("
        "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
        "audit_log_id INTEGER NOT NULL UNIQUE, "
        "occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "actor_user_id CHAR(32), "
        "category VARCHAR(32) NOT NULL, "
        "action VARCHAR(160) NOT NULL, "
        "resource_type VARCHAR(160) NOT NULL, "
        "resource_id VARCHAR(256), "
        "CONSTRAINT system_events_category_check CHECK (category IN "
        "('patient_access', 'nursing', 'clinical', 'admissions', 'laboratory', "
        "'pharmacy', 'billing', 'messaging', 'identity', 'configuration')), "
        "FOREIGN KEY(audit_log_id) REFERENCES audit_logs (id) ON DELETE RESTRICT, "
        "FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL)"
    )
    await connection.exec_driver_sql(
        "INSERT INTO system_events "
        "(id, audit_log_id, occurred_at, actor_user_id, category, action, resource_type, resource_id) "
        "SELECT id, audit_log_id, occurred_at, actor_user_id, category, action, "
        "resource_type, resource_id FROM system_events_before_clinic_management"
    )
    await connection.exec_driver_sql("DROP TABLE system_events_before_clinic_management")
    await connection.exec_driver_sql(
        "CREATE INDEX system_events_category_id_idx ON system_events (category, id)"
    )


async def migrate_sqlite(engine: AsyncEngine) -> list[str]:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("The SQLite migration command requires HMS_DATABASE_URL to use SQLite.")

    applied: list[str] = []
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version VARCHAR(128) PRIMARY KEY, "
            "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        applied_versions = set(
            (await connection.execute(text("SELECT version FROM schema_migrations"))).scalars()
        )

        await connection.run_sync(Base.metadata.create_all)

        user_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("users")
            }
        )
        if "facility_id" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN facility_id INTEGER "
                "REFERENCES facilities(id) ON DELETE SET NULL"
            )
        if "department" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN department VARCHAR(128)"
            )
        if "is_system_owner" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN is_system_owner BOOLEAN NOT NULL DEFAULT 0"
            )
        if "totp_secret_encrypted" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN totp_secret_encrypted BLOB"
            )
        if "totp_pending_secret_encrypted" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN totp_pending_secret_encrypted BLOB"
            )
        if "totp_enabled_at" not in user_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN totp_enabled_at DATETIME"
            )

        patient_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("patients")
            }
        )
        patient_column_definitions = {
            "next_of_kin_name": "VARCHAR(200)",
            "next_of_kin_phone": "VARCHAR(32)",
            "next_of_kin_relationship": "VARCHAR(32)",
            "next_of_kin_relationship_other": "VARCHAR(100)",
            "nationality": "VARCHAR(80)",
            "document_type": "VARCHAR(40)",
            "document_number": "VARCHAR(100)",
            "marital_status": "VARCHAR(40)",
            "category": "VARCHAR(100)",
            "phone_country_code": "VARCHAR(8) NOT NULL DEFAULT '+254'",
            "city_town": "VARCHAR(100)",
            "sub_county_estate": "VARCHAR(100)",
            "postal_code": "VARCHAR(32)",
            "next_of_kin_phone_country_code": "VARCHAR(8) NOT NULL DEFAULT '+254'",
            "next_of_kin_email": "VARCHAR(320)",
            "next_of_kin_id_number": "VARCHAR(100)",
            "department": "VARCHAR(100)",
            "debtor_account": "VARCHAR(100)",
            "staff_account": "VARCHAR(100)",
            "operating_currency": "VARCHAR(3) NOT NULL DEFAULT 'KES'",
            "legacy_number": "VARCHAR(100)",
            "tax_pin": "VARCHAR(32)",
        }
        for column_name, column_definition in patient_column_definitions.items():
            if column_name not in patient_columns:
                await connection.exec_driver_sql(
                    f"ALTER TABLE patients ADD COLUMN {column_name} {column_definition}"
                )
        if "version" not in patient_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE patients ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )

        visit_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("outpatient_visits")
            }
        )
        if "workflow_state" not in visit_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE outpatient_visits ADD COLUMN workflow_state "
                "VARCHAR(32) NOT NULL DEFAULT 'awaiting_triage'"
            )
            await connection.exec_driver_sql(
                "UPDATE outpatient_visits SET workflow_state = "
                "CASE status WHEN 'completed' THEN 'completed' "
                "WHEN 'cancelled' THEN 'cancelled' ELSE 'awaiting_triage' END"
            )

        consultation_note_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("consultation_notes")
            }
        )
        if "version" not in consultation_note_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE consultation_notes ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )

        outpatient_visit_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("outpatient_visits")
            }
        )
        if "clinic_id" not in outpatient_visit_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE outpatient_visits ADD COLUMN clinic_id INTEGER "
                "REFERENCES clinics(id) ON DELETE RESTRICT"
            )

        if "008_clinic_management" not in applied_versions:
            await _rebuild_system_events_category_check(connection)
        await _seed_clinic_catalog(connection)

        await connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_system_owner "
            "ON users (is_system_owner) WHERE is_system_owner = 1"
        )
        await connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS audit_logs_no_update "
            "BEFORE UPDATE ON audit_logs BEGIN "
            "SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
        )
        await connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete "
            "BEFORE DELETE ON audit_logs BEGIN "
            "SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
        )
        await connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS system_events_no_update "
            "BEFORE UPDATE ON system_events BEGIN "
            "SELECT RAISE(ABORT, 'system_events is append-only'); END"
        )
        await connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS system_events_no_delete "
            "BEFORE DELETE ON system_events BEGIN "
            "SELECT RAISE(ABORT, 'system_events is append-only'); END"
        )

        for version in MIGRATION_VERSIONS:
            if version not in applied_versions:
                await connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": version},
                )
                applied.append(version)

    return applied


async def main() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("Set HMS_DATABASE_URL before applying SQLite migrations.")
    try:
        applied = await migrate_sqlite(engine)
        if applied:
            print("Applied SQLite migrations: " + ", ".join(applied))
        else:
            print("SQLite database is already at the latest migration version.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
