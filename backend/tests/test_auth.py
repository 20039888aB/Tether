import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import password_hasher
from app.core.config import get_settings
from app.db.models import Base, Permission, Role, User
from app.db.session import get_db, get_engine
from app.main import app

TEST_PASSWORD = "This-is-a-test-password-2026!"


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "auth-tests.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            users_read_permission = Permission(
                permission_key="identity.users.read",
                description="Read users",
            )
            audit_read_permission = Permission(
                permission_key="quality-audit.read-only-audit-trail-and-transaction-reports.view",
                description="Read audit logs",
            )
            cashier_payment_permission = Permission(
                permission_key="cash-office.receive-cash-m-pesa-card-payments.add",
                description="Receive payments",
            )
            refund_approval_permission = Permission(
                permission_key="accounts.approve-refunds-and-credit-notes.approve",
                description="Approve refunds",
            )
            receptionist_permissions = [
                Permission(
                    permission_key=key,
                    description=key,
                )
                for key in (
                    "front-office.patient-registration-and-biodata.view",
                    "front-office.patient-registration-and-biodata.add",
                    "front-office.patient-registration-and-biodata.edit",
                    "front-office.search-existing-patient-records.view",
                    "front-office.open-outpatient-visit.view",
                    "front-office.open-outpatient-visit.add",
                    "front-office.open-outpatient-visit.edit",
                )
            ]
            system_admin_role = Role(
                name="System Administrator",
                permissions=[
                    Permission(
                        permission_key=key,
                        description=key,
                    )
                    for key in (
                        "identity.users.manage",
                        "identity.roles.read",
                        "identity.roles.manage",
                    )
                ]
                + [users_read_permission],
            )
            access_role = Role(name="Receptionist")
            access_role.permissions.extend([users_read_permission, *receptionist_permissions])
            cashier_role = Role(name="Cashier", permissions=[cashier_payment_permission])
            finance_manager_role = Role(
                name="Finance Manager",
                permissions=[refund_approval_permission],
            )
            session.add_all(
                [
                    *receptionist_permissions,
                    User(
                        username="reception",
                        email="reception@example.test",
                        password_hash=password_hasher.hash(TEST_PASSWORD),
                        roles=[access_role],
                    ),
                    User(
                        username="nurse",
                        email="nurse@example.test",
                        password_hash=password_hasher.hash(TEST_PASSWORD),
                        roles=[Role(name="Nurse")],
                    ),
                    User(
                        username="sysadmin",
                        email="sysadmin@example.test",
                        password_hash=password_hasher.hash(TEST_PASSWORD),
                        roles=[system_admin_role],
                    ),
                    User(
                        username="root",
                        email="root@example.test",
                        password_hash=password_hasher.hash(TEST_PASSWORD),
                        is_system_owner=True,
                        roles=[Role(name="SuperAdmin")],
                    ),
                    User(
                        username="auditor",
                        email="auditor@example.test",
                        password_hash=password_hasher.hash(TEST_PASSWORD),
                        roles=[
                            Role(
                                name="Internal Auditor",
                                permissions=[audit_read_permission],
                            )
                        ],
                    ),
                    cashier_role,
                    finance_manager_role,
                ]
            )
            await session.commit()

    asyncio.run(seed_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_login_permission_check_and_csrf_protected_logout(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "reception", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]
    assert "httponly" in login_response.headers["set-cookie"].lower()

    current_user_response = client.get("/api/v1/auth/me")
    assert current_user_response.status_code == 200
    assert current_user_response.json()["roles"] == ["Receptionist"]

    users_response = client.get("/api/v1/auth/users")
    assert users_response.status_code == 200
    assert len(users_response.json()) == 5

    denied_logout = client.post("/api/v1/auth/logout")
    assert denied_logout.status_code == 403
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_settings_reload_when_environment_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HMS_DATABASE_URL", "sqlite+aiosqlite:///first.sqlite")
    first_settings = get_settings()
    assert first_settings.database_url == "sqlite+aiosqlite:///first.sqlite"
    first_engine = get_engine()
    assert get_engine() is first_engine

    monkeypatch.setenv("HMS_DATABASE_URL", "sqlite+aiosqlite:///second.sqlite")
    second_settings = get_settings()
    assert second_settings.database_url == "sqlite+aiosqlite:///second.sqlite"
    assert first_settings is not second_settings
    second_engine = get_engine()
    assert second_engine is not first_engine
    asyncio.run(first_engine.dispose())
    asyncio.run(second_engine.dispose())


def test_permission_is_enforced_server_side(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "nurse", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/auth/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "permission_denied"}


def test_receptionist_registers_patient_updates_record_and_opens_opd_visit(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "reception", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    headers = {"X-CSRF-Token": login_response.json()["csrf_token"]}
    patient_data = {
        "first_name": "Jamie",
        "middle_name": "Synthetic",
        "last_name": "Example",
        "date_of_birth": "1990-04-12",
        "sex_at_birth": "unknown",
        "phone_number": "+254700123456",
        "email": "jamie@example.test",
        "address": "Synthetic test address",
    }

    create_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json=patient_data,
    )

    assert create_response.status_code == 201
    patient = create_response.json()
    assert patient["patient_number"].startswith("TTH-")
    assert patient["first_name"] == "Jamie"
    assert client.get("/api/v1/patients?q=Jamie").json()["total"] == 1

    update_response = client.put(
        f"/api/v1/patients/{patient['id']}",
        headers=headers,
        json={**patient_data, "address": "Updated synthetic address"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["address"] == "Updated synthetic address"

    visit_response = client.post(
        "/api/v1/outpatient-visits",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "clinic": "General practice",
            "visit_type": "Consultation",
        },
    )
    assert visit_response.status_code == 201
    visit = visit_response.json()
    assert visit["patient_id"] == patient["id"]
    assert visit["patient_number"] == patient["patient_number"]
    assert visit["status"] == "queued"

    queue_response = client.get("/api/v1/outpatient-visits?status=queued")
    assert queue_response.status_code == 200
    assert queue_response.json()["items"][0]["visit_number"] == visit["visit_number"]
    assert client.get(f"/api/v1/patients/{patient['id']}").status_code == 200

    duplicate_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json=patient_data,
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "possible_duplicate_patient"}

    client.cookies.clear()
    root_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert root_login.status_code == 200
    assert client.get("/api/v1/patients").status_code == 200
    assert client.get("/api/v1/outpatient-visits").status_code == 200
    audit_response = client.get("/api/v1/auth/audit-logs?limit=100&offset=0")
    actions = {entry["action"] for entry in audit_response.json()["items"]}
    assert "patient.registration.create" in actions
    assert "patient.registration.update" in actions
    assert "patient.record.read" in actions
    assert "outpatient.visit.create" in actions


def test_patient_and_opd_apis_reject_users_without_the_required_permission(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "nurse", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    assert client.get("/api/v1/patients").status_code == 403
    assert client.get("/api/v1/outpatient-visits").status_code == 403


def test_internal_auditor_can_read_audit_logs_but_not_user_accounts(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "auditor", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    audit_response = client.get("/api/v1/auth/audit-logs?limit=10&offset=0")

    assert audit_response.status_code == 200
    assert audit_response.json()["total"] >= 1
    assert audit_response.json()["items"][0]["actor_username"] == "auditor"
    assert audit_response.json()["items"][0]["action"] == "authentication.login"
    assert "metadata" not in audit_response.json()["items"][0]
    assert client.get("/api/v1/auth/users").status_code == 403


def test_superadmin_user_permission_overrides_are_immediate_and_precede_roles(
    client: TestClient,
) -> None:
    settings = get_settings()
    reception_login = client.post(
        "/api/v1/auth/login",
        json={"username": "reception", "password": TEST_PASSWORD},
    )
    assert reception_login.status_code == 200
    reception_session = client.cookies.get(settings.session_cookie_name)
    assert reception_session is not None
    reception_id = client.get("/api/v1/auth/me").json()["id"]

    client.cookies.clear()
    root_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert root_login.status_code == 200
    response = client.put(
        f"/api/v1/auth/users/{reception_id}/permissions",
        headers={"X-CSRF-Token": root_login.json()["csrf_token"]},
        json={
            "overrides": {
                "identity.users.read": False,
                "front-office.search-existing-patient-records.view": True,
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["permission_overrides"] == {
        "identity.users.read": False,
        "front-office.search-existing-patient-records.view": True,
    }

    client.cookies.clear()
    client.cookies.set(settings.session_cookie_name, reception_session)
    profile = client.get("/api/v1/auth/me")
    assert profile.status_code == 200
    assert "identity.users.read" not in profile.json()["permissions"]
    assert "front-office.search-existing-patient-records.view" in profile.json()["permissions"]
    assert client.get("/api/v1/auth/users").status_code == 403

    client.cookies.clear()
    system_admin = client.post(
        "/api/v1/auth/login",
        json={"username": "sysadmin", "password": TEST_PASSWORD},
    )
    assert system_admin.status_code == 200
    denied_policy_update = client.put(
        f"/api/v1/auth/users/{reception_id}/permissions",
        headers={"X-CSRF-Token": system_admin.json()["csrf_token"]},
        json={"overrides": {}},
    )
    assert denied_policy_update.status_code == 403


def test_admin_password_reset_revokes_sessions_and_rejects_superadmin(
    client: TestClient,
) -> None:
    receptionist_login = client.post(
        "/api/v1/auth/login",
        json={"username": "reception", "password": TEST_PASSWORD},
    )
    assert receptionist_login.status_code == 200
    settings = get_settings()
    receptionist_session_cookie = client.cookies.get(settings.session_cookie_name)
    assert receptionist_session_cookie is not None

    client.cookies.clear()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "sysadmin", "password": TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_session_cookie = client.cookies.get(settings.session_cookie_name)
    assert admin_session_cookie is not None
    admin_headers = {"X-CSRF-Token": admin_login.json()["csrf_token"]}
    users = client.get("/api/v1/auth/users").json()
    receptionist = next(user for user in users if user["username"] == "reception")
    superadmin = next(user for user in users if user["username"] == "root")

    reset_response = client.put(
        f"/api/v1/auth/users/{receptionist['id']}/password",
        headers=admin_headers,
        json={"password": "Replacement-Password-2026!"},
    )

    assert reset_response.status_code == 204
    client.cookies.clear()
    client.cookies.set(settings.session_cookie_name, receptionist_session_cookie)
    assert (
        client.get(
            "/api/v1/auth/me",
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "reception", "password": TEST_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "reception", "password": "Replacement-Password-2026!"},
        ).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.set(settings.session_cookie_name, admin_session_cookie)
    client.cookies.set(settings.csrf_cookie_name, admin_login.json()["csrf_token"])
    assert (
        client.put(
            f"/api/v1/auth/users/{superadmin['id']}/password",
            headers=admin_headers,
            json={"password": "Replacement-Password-2026!"},
        ).status_code
        == 403
    )


def test_user_cannot_have_cashier_and_refund_approver_permissions(
    client: TestClient,
) -> None:
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    headers = {"X-CSRF-Token": admin_login.json()["csrf_token"]}
    roles = client.get("/api/v1/auth/roles").json()
    conflicting_role_ids = [
        role["id"] for role in roles if role["name"] in {"Cashier", "Finance Manager"}
    ]

    response = client.post(
        "/api/v1/auth/users",
        headers=headers,
        json={
            "username": "conflicted",
            "email": "conflicted@example.test",
            "password": "Initial-Staff-Password-2026!",
            "role_ids": conflicting_role_ids,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "separation_of_duties_conflict:cashier_refund_approval"
    }

    cashier_role = next(role for role in roles if role["name"] == "Cashier")
    companion_role = client.post(
        "/api/v1/auth/roles",
        headers=headers,
        json={"name": "Cashier companion", "description": "", "permission_keys": []},
    )
    assert companion_role.status_code == 201
    companion_user = client.post(
        "/api/v1/auth/users",
        headers=headers,
        json={
            "username": "cashier-companion",
            "email": "cashier-companion@example.test",
            "password": "Initial-Staff-Password-2026!",
            "role_ids": [cashier_role["id"], companion_role.json()["id"]],
        },
    )
    assert companion_user.status_code == 201
    conflicting_override = client.put(
        f"/api/v1/auth/users/{companion_user.json()['id']}/permissions",
        headers=headers,
        json={
            "overrides": {
                "accounts.approve-refunds-and-credit-notes.approve": True
            }
        },
    )
    assert conflicting_override.status_code == 409
    assert conflicting_override.json() == {
        "detail": "separation_of_duties_conflict:cashier_refund_approval"
    }

    role_update_response = client.put(
        f"/api/v1/auth/roles/{companion_role.json()['id']}/permissions",
        headers=headers,
        json={
            "permission_keys": [
                "accounts.approve-refunds-and-credit-notes.approve"
            ]
        },
    )
    assert role_update_response.status_code == 409
    assert role_update_response.json() == {
        "detail": "separation_of_duties_conflict:cashier_refund_approval"
    }


def test_failed_logins_trigger_temporary_account_lockout(client: TestClient) -> None:
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "reception", "password": "incorrect-password"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/auth/login",
        json={"username": "reception", "password": TEST_PASSWORD},
    )

    assert locked_response.status_code == 401
    assert locked_response.json() == {"detail": "invalid_credentials"}


def test_superadmin_can_create_role_and_admin_can_manage_users(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    role_response = client.post(
        "/api/v1/auth/roles",
        headers=headers,
        json={
            "name": "Reception Manager",
            "description": "Patient registration oversight",
            "permission_keys": ["front-office.patient-registration-and-biodata.view"],
        },
    )
    assert role_response.status_code == 201
    role = role_response.json()

    create_user_response = client.post(
        "/api/v1/auth/users",
        headers=headers,
        json={
            "username": "newstaff",
            "email": "newstaff@example.test",
            "department": "Front Office",
            "password": "Initial-Staff-Password-2026!",
            "role_ids": [role["id"]],
        },
    )
    assert create_user_response.status_code == 201
    user = create_user_response.json()
    assert user["roles"] == ["Reception Manager"]
    assert user["department"] == "Front Office"
    assert "password" not in user

    user_login = client.post(
        "/api/v1/auth/login",
        json={"username": "newstaff", "password": "Initial-Staff-Password-2026!"},
    )
    assert user_login.status_code == 200
    profile = client.get("/api/v1/auth/me")
    assert profile.status_code == 200
    assert profile.json()["roles"] == ["Reception Manager"]
    assert profile.json()["permissions"] == [
        "front-office.patient-registration-and-biodata.view"
    ]
    assert client.get("/api/v1/auth/users").status_code == 403
    assert client.get("/api/v1/auth/roles").status_code == 403

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    admin_headers = {"X-CSRF-Token": admin_login.json()["csrf_token"]}
    second_role_response = client.post(
        "/api/v1/auth/roles",
        headers=admin_headers,
        json={
            "name": "Patient Searcher",
            "description": "Search existing patient records",
            "permission_keys": ["front-office.search-existing-patient-records.view"],
        },
    )
    assert second_role_response.status_code == 201
    second_role = second_role_response.json()
    client.cookies.clear()
    system_admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "sysadmin", "password": TEST_PASSWORD},
    )
    assert system_admin_login.status_code == 200
    admin_headers = {"X-CSRF-Token": system_admin_login.json()["csrf_token"]}
    role_assignment_response = client.put(
        f"/api/v1/auth/users/{user['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [second_role["id"]]},
    )
    assert role_assignment_response.status_code == 200
    assert role_assignment_response.json()["roles"] == ["Patient Searcher"]

    client.cookies.clear()
    root_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    root_headers = {"X-CSRF-Token": root_login.json()["csrf_token"]}
    update_role_response = client.put(
        f"/api/v1/auth/roles/{second_role['id']}/permissions",
        headers=root_headers,
        json={"permission_keys": ["identity.users.read"]},
    )
    assert update_role_response.status_code == 200
    profile_update = client.put(
        f"/api/v1/auth/users/{user['id']}",
        headers=root_headers,
        json={
            "username": "newstaff",
            "email": "newstaff@example.test",
            "department": "Outpatient",
        },
    )
    assert profile_update.status_code == 200
    assert profile_update.json()["department"] == "Outpatient"

    updated_user_login = client.post(
        "/api/v1/auth/login",
        json={"username": "newstaff", "password": "Initial-Staff-Password-2026!"},
    )
    assert updated_user_login.status_code == 200
    assert "identity.users.read" in client.get("/api/v1/auth/me").json()["permissions"]
    assert client.get("/api/v1/auth/users").status_code == 200

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "sysadmin", "password": TEST_PASSWORD},
    )
    deactivate_response = client.patch(
        f"/api/v1/auth/users/{user['id']}/status",
        headers={"X-CSRF-Token": admin_login.json()["csrf_token"]},
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    deactivated_login = client.post(
        "/api/v1/auth/login",
        json={"username": "newstaff", "password": "Initial-Staff-Password-2026!"},
    )
    assert deactivated_login.status_code == 401


def test_superadmin_has_full_access_and_only_superadmin_policy_changes(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    headers = {"X-CSRF-Token": login_response.json()["csrf_token"]}

    users_response = client.get("/api/v1/auth/users")
    assert users_response.status_code == 200
    roles_response = client.get("/api/v1/auth/roles")
    assert roles_response.status_code == 200
    superadmin_role = next(
        role for role in roles_response.json() if role["name"] == "SuperAdmin"
    )
    root_id = next(
        user["id"] for user in users_response.json() if user["username"] == "root"
    )
    assert client.put(
        f"/api/v1/auth/roles/{superadmin_role['id']}/permissions",
        headers=headers,
        json={"permission_keys": []},
    ).status_code == 403
    assert client.put(
        f"/api/v1/auth/users/{root_id}/roles",
        headers=headers,
        json={"role_ids": []},
    ).status_code == 409
    assert client.patch(
        f"/api/v1/auth/users/{root_id}/status",
        headers=headers,
        json={"is_active": False},
    ).status_code == 409
    assert client.put(
        f"/api/v1/auth/users/{root_id}/permissions",
        headers=headers,
        json={"overrides": {}},
    ).status_code == 409

    reserved_role_response = client.post(
        "/api/v1/auth/roles",
        headers=headers,
        json={"name": "superadmin", "description": "", "permission_keys": []},
    )
    assert reserved_role_response.status_code == 403

    client.cookies.clear()
    system_admin_login = client.post(
        "/api/v1/auth/login",
        json={"username": "sysadmin", "password": TEST_PASSWORD},
    )
    system_admin_headers = {"X-CSRF-Token": system_admin_login.json()["csrf_token"]}
    assert client.post(
        "/api/v1/auth/roles",
        headers=system_admin_headers,
        json={"name": "Unauthorized role", "description": "", "permission_keys": []},
    ).status_code == 403
    assert client.put(
        f"/api/v1/auth/users/{root_id}/permissions",
        headers=system_admin_headers,
        json={"overrides": {}},
    ).status_code == 403

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    headers = {"X-CSRF-Token": login_response.json()["csrf_token"]}

    assigned_superadmin_response = client.post(
        "/api/v1/auth/users",
        headers=headers,
        json={
            "username": "secondroot",
            "email": "secondroot@example.test",
            "password": "Initial-Staff-Password-2026!",
            "role_ids": [superadmin_role["id"]],
        },
    )
    assert assigned_superadmin_response.status_code == 201
    assert assigned_superadmin_response.json()["roles"] == ["SuperAdmin"]
    assert assigned_superadmin_response.json()["is_system_owner"] is False

    client.cookies.clear()
    secondroot_login = client.post(
        "/api/v1/auth/login",
        json={"username": "secondroot", "password": "Initial-Staff-Password-2026!"},
    )
    secondroot_headers = {"X-CSRF-Token": secondroot_login.json()["csrf_token"]}
    assert client.get("/api/v1/auth/me").json()["is_system_owner"] is False
    assert client.put(
        f"/api/v1/auth/users/{root_id}/roles",
        headers=secondroot_headers,
        json={"role_ids": []},
    ).status_code == 403
    assert client.patch(
        f"/api/v1/auth/users/{root_id}/status",
        headers=secondroot_headers,
        json={"is_active": False},
    ).status_code == 403
    assert client.put(
        f"/api/v1/auth/users/{root_id}/permissions",
        headers=secondroot_headers,
        json={"overrides": {}},
    ).status_code == 409

    client.cookies.clear()
    owner_login = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    owner_headers = {"X-CSRF-Token": owner_login.json()["csrf_token"]}
    owner_profile = client.get("/api/v1/auth/me").json()
    assert owner_profile["is_system_owner"] is True
    assert "SuperAdmin" in owner_profile["roles"]
    assert client.put(
        f"/api/v1/auth/users/{root_id}/roles",
        headers=owner_headers,
        json={"role_ids": []},
    ).status_code == 409
    assert client.patch(
        f"/api/v1/auth/users/{root_id}/status",
        headers=owner_headers,
        json={"is_active": False},
    ).status_code == 409


def test_superadmin_can_manage_custom_roles_and_permissions(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    headers = {"X-CSRF-Token": login_response.json()["csrf_token"]}

    permission_response = client.post(
        "/api/v1/auth/permissions",
        headers=headers,
        json={"key": "custom.patient-records.view", "description": "View custom records"},
    )
    assert permission_response.status_code == 201
    permission = permission_response.json()

    role_response = client.post(
        "/api/v1/auth/roles",
        headers=headers,
        json={
            "name": "Custom Records Reviewer",
            "description": "Initial description",
            "permission_keys": [permission["key"]],
        },
    )
    assert role_response.status_code == 201
    role = role_response.json()

    updated_permission = client.put(
        f"/api/v1/auth/permissions/{permission['id']}",
        headers=headers,
        json={
            "key": "custom.patient-records.review",
            "description": "Review custom records",
        },
    )
    assert updated_permission.status_code == 200

    updated_role = client.put(
        f"/api/v1/auth/roles/{role['id']}",
        headers=headers,
        json={"name": "Records Reviewer", "description": "Updated description"},
    )
    assert updated_role.status_code == 200
    assert updated_role.json()["permissions"] == ["custom.patient-records.review"]

    assert client.delete(
        f"/api/v1/auth/roles/{role['id']}",
        headers=headers,
    ).status_code == 204
    assert client.delete(
        f"/api/v1/auth/permissions/{permission['id']}",
        headers=headers,
    ).status_code == 204


def test_superadmin_can_reset_own_password_and_session_is_revoked(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    root_id = client.get("/api/v1/auth/me").json()["id"]
    replacement_password = "Replacement-Root-Password-2026!"

    response = client.put(
        f"/api/v1/auth/users/{root_id}/password",
        headers={"X-CSRF-Token": login_response.json()["csrf_token"]},
        json={"password": replacement_password},
    )

    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "root", "password": replacement_password},
    ).status_code == 200
