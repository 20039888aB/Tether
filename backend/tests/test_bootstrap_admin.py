import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.bootstrap_admin import recover_system_owner
from app.db.models import AuditLog, AuthSession, Base, Role, User


def test_system_owner_recovery_restores_access_and_revokes_sessions(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'owner-recovery.sqlite'}"
    monkeypatch.setenv("HMS_DATABASE_URL", database_url)
    password = "Recovered-owner-password-2026!"

    async def seed_database() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            superadmin_role = Role(name="SuperAdmin")
            owner = User(
                username="owner",
                email="owner@example.test",
                password_hash=PasswordHasher().hash("Original-owner-password-2026!"),
                is_system_owner=True,
                is_active=False,
                failed_login_attempts=5,
                locked_until=datetime.now(UTC) + timedelta(minutes=15),
                totp_secret_encrypted=b"encrypted-totp-secret",
                totp_pending_secret_encrypted=b"pending-totp-secret",
                totp_enabled_at=datetime.now(UTC),
                roles=[],
            )
            session.add_all([owner, superadmin_role])
            await session.flush()
            session.add(
                AuthSession(
                    user_id=owner.id,
                    token_hash=b"session-token-hash",
                    csrf_token_hash=b"csrf-token-hash",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_database())
    asyncio.run(recover_system_owner(password, password))

    async def assert_recovery() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            owner = await session.scalar(
                select(User).options(selectinload(User.roles)).where(User.username == "owner")
            )
            assert owner is not None
            assert owner.is_system_owner is True
            assert owner.is_active is True
            assert owner.failed_login_attempts == 0
            assert owner.locked_until is None
            assert owner.totp_secret_encrypted is None
            assert owner.totp_pending_secret_encrypted is None
            assert owner.totp_enabled_at is None
            assert any(role.name == "SuperAdmin" for role in owner.roles)
            assert PasswordHasher().verify(owner.password_hash, password)

            auth_session = await session.scalar(select(AuthSession))
            assert auth_session is not None
            assert auth_session.revoked_at is not None
            audit = await session.scalar(
                select(AuditLog).where(AuditLog.action == "identity.system_owner.recovery")
            )
            assert audit is not None
        await engine.dispose()

    asyncio.run(assert_recovery())


def test_system_owner_recovery_rejects_mismatched_passwords() -> None:
    with pytest.raises(ValueError, match="Passwords do not match"):
        asyncio.run(recover_system_owner("A-valid-password-2026!", "Different-password-2026!"))
