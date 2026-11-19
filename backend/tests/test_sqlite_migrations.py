import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.migrate_sqlite import MIGRATION_VERSIONS, migrate_sqlite


def test_sqlite_migrations_are_repeatable(tmp_path) -> None:
    database_path = tmp_path / "migration-test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    try:
        first = asyncio.run(migrate_sqlite(engine))
        second = asyncio.run(migrate_sqlite(engine))

        assert first == list(MIGRATION_VERSIONS)
        assert second == []

        async def inspect_database() -> tuple[list[str], int, set[str]]:
            async with engine.connect() as connection:
                tables = set(
                    (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE type = 'table'")
                        )
                    ).scalars()
                )
                applied_count = (
                    await connection.scalar(text("SELECT COUNT(*) FROM schema_migrations"))
                    or 0
                )
                user_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("users")
                    }
                )
            return sorted(tables), applied_count, user_columns

        tables, applied_count, user_columns = asyncio.run(inspect_database())
        assert {
            "users",
            "roles",
            "permissions",
            "user_roles",
            "role_permissions",
            "user_permission_overrides",
            "auth_sessions",
            "audit_logs",
            "patients",
            "outpatient_visits",
            "visit_triages",
            "consultation_notes",
            "system_events",
            "facilities",
            "clinics",
            "visit_types",
            "clinic_visit_types",
            "facility_clinics",
            "doctor_clinics",
            "patient_number_counters",
            "schema_migrations",
        }.issubset(tables)
        assert applied_count == len(MIGRATION_VERSIONS)
        assert {
            "totp_secret_encrypted",
            "totp_pending_secret_encrypted",
            "totp_enabled_at",
        }.issubset(user_columns)

        async def inspect_clinical_columns() -> tuple[set[str], set[str], set[str]]:
            async with engine.connect() as connection:
                patient_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("patients")
                    }
                )
                visit_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("outpatient_visits")
                    }
                )
                note_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("consultation_notes")
                    }
                )
            return patient_columns, visit_columns, note_columns

        patient_columns, visit_columns, note_columns = asyncio.run(inspect_clinical_columns())
        assert {
            "next_of_kin_name",
            "next_of_kin_phone",
            "next_of_kin_relationship",
            "next_of_kin_relationship_other",
        }.issubset(patient_columns)
        assert "version" in patient_columns
        assert {
            "nationality",
            "document_type",
            "phone_country_code",
            "city_town",
            "department",
            "next_of_kin_email",
        }.issubset(patient_columns)
        assert "workflow_state" in visit_columns
        assert "clinic_id" in visit_columns
        assert "version" in note_columns

        async def count_seeded_clinics() -> tuple[int, int, str]:
            async with engine.connect() as connection:
                clinic_count = await connection.scalar(text("SELECT COUNT(*) FROM clinics")) or 0
                facility_clinic_count = (
                    await connection.scalar(text("SELECT COUNT(*) FROM facility_clinics")) or 0
                )
                clinic_category = await connection.scalar(
                    text(
                        "SELECT v.name FROM clinic_visit_types cv "
                        "JOIN clinics c ON c.id = cv.clinic_id "
                        "JOIN visit_types v ON v.id = cv.visit_type_id "
                        "WHERE c.code = 'ANTENATAL'"
                    )
                )
            return clinic_count, facility_clinic_count, clinic_category

        assert asyncio.run(count_seeded_clinics()) == (
            35,
            35,
            "1ST ANC VISIT (0-12 WEEKS)",
        )
    finally:
        asyncio.run(engine.dispose())


def test_sqlite_migration_adds_totp_columns_to_existing_schema(tmp_path) -> None:
    database_path = tmp_path / "existing-schema.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def create_previous_schema() -> None:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE users ("
                "id CHAR(32) PRIMARY KEY, username VARCHAR(128), email VARCHAR(320), "
                "department VARCHAR(128), password_hash TEXT, "
                "is_system_owner BOOLEAN NOT NULL DEFAULT 0, "
                "is_active BOOLEAN NOT NULL DEFAULT 1, "
                "failed_login_attempts INTEGER NOT NULL DEFAULT 0, "
                "locked_until DATETIME, created_at DATETIME, updated_at DATETIME)"
            )
            await connection.exec_driver_sql(
                "CREATE TABLE patients ("
                "id CHAR(32) PRIMARY KEY, patient_number VARCHAR(40), "
                "first_name VARCHAR(100), last_name VARCHAR(100))"
            )
            await connection.exec_driver_sql(
                "CREATE TABLE outpatient_visits ("
                "id CHAR(32) PRIMARY KEY, patient_id CHAR(32), visit_number VARCHAR(40), "
                "clinic VARCHAR(128), visit_type VARCHAR(64), status VARCHAR(16) "
                "CHECK (status IN ('queued', 'cancelled', 'completed')))"
            )
            await connection.exec_driver_sql(
                "INSERT INTO patients (id, patient_number, first_name, last_name) "
                "VALUES ('patient-id', 'TTH-OLD', 'Legacy', 'Patient')"
            )
            await connection.exec_driver_sql(
                "INSERT INTO outpatient_visits "
                "(id, patient_id, visit_number, clinic, visit_type, status) "
                "VALUES ('visit-id', 'patient-id', 'OPD-OLD', 'General', 'Consultation', 'queued')"
            )
            await connection.exec_driver_sql(
                "CREATE TABLE schema_migrations "
                "(version VARCHAR(128) PRIMARY KEY, applied_at DATETIME)"
            )
            for version in MIGRATION_VERSIONS[:-1]:
                await connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": version},
                )

    try:
        asyncio.run(create_previous_schema())
        assert asyncio.run(migrate_sqlite(engine)) == ["008_clinic_management"]

        async def read_user_columns() -> set[str]:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("users")
                    }
                )

        user_columns = asyncio.run(read_user_columns())
        assert "totp_secret_encrypted" in user_columns
        assert "totp_pending_secret_encrypted" in user_columns
        assert "totp_enabled_at" in user_columns

        async def read_migrated_visit() -> tuple[str, str, str]:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT patients.patient_number, patients.next_of_kin_name, "
                            "outpatient_visits.workflow_state "
                            "FROM patients JOIN outpatient_visits "
                            "ON patients.id = outpatient_visits.patient_id "
                            "WHERE outpatient_visits.id = 'visit-id'"
                        )
                    )
                ).one()
            return row[0], row[1], row[2]

        assert asyncio.run(read_migrated_visit()) == ("TTH-OLD", None, "awaiting_triage")

        async def advance_visit() -> None:
            async with engine.begin() as connection:
                await connection.exec_driver_sql(
                    "UPDATE outpatient_visits SET workflow_state = 'awaiting_doctor' "
                    "WHERE id = 'visit-id'"
                )

        asyncio.run(advance_visit())
        assert asyncio.run(migrate_sqlite(engine)) == []
        assert asyncio.run(read_migrated_visit()) == ("TTH-OLD", None, "awaiting_doctor")
    finally:
        asyncio.run(engine.dispose())
