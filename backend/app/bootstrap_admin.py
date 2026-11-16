import argparse
import asyncio
from datetime import UTC, datetime
from getpass import getpass

from argon2 import PasswordHasher
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.models import AuditLog, AuthSession, Role, User
from app.db.session import get_engine


async def create_super_admin() -> None:
    username = input("Administrator username: ").strip()
    email = input("Administrator email: ").strip().lower()
    if not username or not email:
        raise ValueError("Administrator username and email are required.")
    password = getpass("Password (minimum 14 characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 14:
        raise ValueError("Administrator password must be at least 14 characters.")
    if password != confirmation:
        raise ValueError("Passwords do not match.")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("Set HMS_DATABASE_URL before creating the first administrator.")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            existing = await session.scalar(select(User.id).where(User.username == username))
            if existing is not None:
                raise ValueError("That username already exists.")
            existing_admin = await session.scalar(
                select(User.id)
                .join(User.roles)
                .where(Role.name == "SuperAdmin")
                .limit(1)
            )
            if existing_admin is not None:
                raise ValueError("A SuperAdmin already exists; use the approved account workflow.")

            role = await session.scalar(select(Role).where(Role.name == "SuperAdmin"))
            if role is None:
                raise RuntimeError(
                    "Apply the core database migration before bootstrapping an administrator."
                )

            admin = User(
                username=username,
                email=email,
                password_hash=PasswordHasher().hash(password),
                is_system_owner=True,
                roles=[role],
            )
            session.add(admin)
            await session.flush()
            session.add(
                AuditLog(
                    actor_user_id=admin.id,
                    action="identity.super_admin_bootstrap",
                    resource_type="user",
                    resource_id=str(admin.id),
                    outcome="success",
                    event_metadata={"bootstrap": True},
                )
            )
            await session.commit()
    finally:
        await engine.dispose()
    print(
        "Initial administrator created. Remove the bootstrap command from the operational runbook."
    )


async def recover_system_owner(password: str, confirmation: str) -> None:
    if len(password) < 14:
        raise ValueError("Administrator password must be at least 14 characters.")
    if password != confirmation:
        raise ValueError("Passwords do not match.")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("Set HMS_DATABASE_URL before recovering the system owner.")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            owner = await session.scalar(
                select(User)
                .options(selectinload(User.roles))
                .where(User.is_system_owner.is_(True))
            )
            if owner is None:
                raise RuntimeError("No system owner is configured.")

            superadmin_role = await session.scalar(
                select(Role).where(Role.name == "SuperAdmin")
            )
            if superadmin_role is None:
                raise RuntimeError("The SuperAdmin role is not seeded.")
            if all(role.name != "SuperAdmin" for role in owner.roles):
                owner.roles.append(superadmin_role)

            owner.password_hash = PasswordHasher().hash(password)
            owner.is_active = True
            owner.failed_login_attempts = 0
            owner.locked_until = None
            await session.execute(
                update(AuthSession)
                .where(AuthSession.user_id == owner.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            session.add(
                AuditLog(
                    actor_user_id=owner.id,
                    action="identity.system_owner.recovery",
                    resource_type="user",
                    resource_id=str(owner.id),
                    outcome="success",
                    event_metadata={"recovery": True},
                )
            )
            await session.commit()
            username = owner.username
    finally:
        await engine.dispose()
    print(f"System owner account '{username}' recovered; existing sessions were revoked.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap or recover the TETHER system owner.")
    parser.add_argument(
        "--recover-owner",
        action="store_true",
        help="Reset the existing system owner's password and login lockout.",
    )
    arguments = parser.parse_args()
    if arguments.recover_owner:
        password = getpass("New owner password (minimum 14 characters): ")
        confirmation = getpass("Confirm new owner password: ")
        asyncio.run(recover_system_owner(password, confirmation))
    else:
        asyncio.run(create_super_admin())


if __name__ == "__main__":
    main()
