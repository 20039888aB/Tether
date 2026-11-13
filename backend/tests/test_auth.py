import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import password_hasher
from app.db.models import Base, Permission, Role, User
from app.db.session import get_db
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
            access_role = Role(name="Receptionist")
            access_role.permissions.append(
                Permission(permission_key="identity.users.read", description="Read users")
            )
            session.add_all(
                [
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
    assert len(users_response.json()) == 2

    denied_logout = client.post("/api/v1/auth/logout")
    assert denied_logout.status_code == 403
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_permission_is_enforced_server_side(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "nurse", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/auth/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "permission_denied"}


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
