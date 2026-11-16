import asyncio

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.rbac import ROLE_DESCRIPTIONS, default_role_permissions, permission_catalog
from app.db.models import Base, Permission, Role, User
from app.db.session import get_engine

LEGACY_ROLE_NAMES = {
    "Admin": "System Administrator",
    "Doctor": "Doctor / Medical Officer",
    "LabTech": "Laboratory Technologist",
    "HRManager": "HR Manager",
}
LEGACY_ROLE_DESCRIPTIONS = {
    "Accountant": "Restricted accounting workflows",
    "Cashier": "Payment collection workflows",
    "Nurse": "Nursing workflows",
    "Pharmacist": "Pharmacy workflows",
    "Receptionist": "Patient access workflows",
}


async def seed_role_catalog() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("Set HMS_DATABASE_URL before seeding the role catalog.")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if engine.dialect.name == "sqlite":
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
                user_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("users")
                    }
                )
                if "department" not in user_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE users ADD COLUMN department VARCHAR(128)"
                    )
                if "is_system_owner" not in user_columns:
                    await connection.exec_driver_sql(
                        "ALTER TABLE users ADD COLUMN is_system_owner BOOLEAN NOT NULL DEFAULT 0"
                    )
                await connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_system_owner "
                    "ON users (is_system_owner) WHERE is_system_owner = 1"
                )
        async with session_factory() as session:
            permissions = (await session.scalars(select(Permission))).all()
            permission_by_key = {
                permission.permission_key: permission for permission in permissions
            }
            catalog = permission_catalog()
            for key, description in catalog.items():
                if key not in permission_by_key:
                    permission = Permission(permission_key=key, description=description)
                    session.add(permission)
                    permission_by_key[key] = permission

            existing_roles = (
                await session.scalars(
                    select(Role).options(
                        selectinload(Role.permissions),
                        selectinload(Role.users),
                    )
                )
            ).all()
            roles_by_name = {role.name: role for role in existing_roles}
            new_role_names: set[str] = set()
            migrated_role_names = {
                name
                for name, description in LEGACY_ROLE_DESCRIPTIONS.items()
                if name in roles_by_name and roles_by_name[name].description == description
            }
            for old_name, canonical_name in LEGACY_ROLE_NAMES.items():
                legacy_role = roles_by_name.get(old_name)
                if legacy_role is None:
                    continue
                canonical_role = roles_by_name.get(canonical_name)
                if canonical_role is None:
                    legacy_role.name = canonical_name
                    legacy_role.description = ROLE_DESCRIPTIONS[canonical_name]
                    roles_by_name.pop(old_name)
                    roles_by_name[canonical_name] = legacy_role
                    migrated_role_names.add(canonical_name)
                else:
                    for user in legacy_role.users:
                        if user not in canonical_role.users:
                            canonical_role.users.append(user)
                    await session.delete(legacy_role)
                    roles_by_name.pop(old_name)
                    migrated_role_names.add(canonical_name)

            for name, description in ROLE_DESCRIPTIONS.items():
                role = roles_by_name.get(name)
                if role is None:
                    role = Role(name=name, description=description)
                    roles_by_name[name] = role
                    new_role_names.add(name)

            default_grants = default_role_permissions()
            for name, grant_keys in default_grants.items():
                role = roles_by_name[name]
                if name == "SuperAdmin":
                    role.permissions = list(permission_by_key.values())
                elif name in new_role_names or name in migrated_role_names:
                    role.permissions = [permission_by_key[key] for key in grant_keys]
                else:
                    existing_keys = {permission.permission_key for permission in role.permissions}
                    role.permissions.extend(
                        permission_by_key[key]
                        for key in grant_keys - existing_keys
                    )
                if name in new_role_names:
                    session.add(role)

            owner = await session.scalar(
                select(User).where(User.is_system_owner.is_(True))
            )
            configured_owner = get_settings().system_owner_username
            if owner is None:
                active_superadmins = (
                    await session.scalars(
                        select(User)
                        .join(User.roles)
                        .options(selectinload(User.roles))
                        .where(User.is_active.is_(True), Role.name == "SuperAdmin")
                    )
                ).unique().all()
                if configured_owner:
                    owner = next(
                        (
                            user
                            for user in active_superadmins
                            if user.username.casefold() == configured_owner.strip().casefold()
                        ),
                        None,
                    )
                    if owner is None:
                        raise RuntimeError(
                            "HMS_SYSTEM_OWNER_USERNAME must identify an active SuperAdmin."
                        )
                elif len(active_superadmins) == 1:
                    owner = active_superadmins[0]
                elif len(active_superadmins) > 1:
                    raise RuntimeError(
                        "Set HMS_SYSTEM_OWNER_USERNAME to identify the owner among existing "
                        "SuperAdmin accounts."
                    )
                if owner is not None:
                    owner.is_system_owner = True

            await session.commit()
            print(f"Seeded {len(catalog)} catalog permissions and {len(ROLE_DESCRIPTIONS)} roles.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_role_catalog())
