import asyncio
from getpass import getpass

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AuditLog, Role, User
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


if __name__ == "__main__":
    asyncio.run(create_super_admin())
