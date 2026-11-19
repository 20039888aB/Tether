import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.rbac import permission_catalog, separation_of_duties_conflict
from app.core.system_events import attach_operation_event
from app.db.models import (
    AuditLog,
    AuthSession,
    Facility,
    Permission,
    Role,
    User,
    UserPermissionOverride,
)
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))
DbSession = Annotated[AsyncSession, Depends(get_db)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)
    totp_code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=14, max_length=1024)
    department: str | None = Field(default=None, max_length=128)
    facility_id: int | None = Field(default=None, ge=1)
    role_ids: list[UUID] = Field(min_length=1)

    @field_validator("username", "email")
    @classmethod
    def normalize_identity_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @field_validator("department")
    @classmethod
    def normalize_department(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        if "@" not in value or any(character.isspace() for character in value):
            raise ValueError("Enter a valid email address.")
        return value.lower()


class UserRolesRequest(BaseModel):
    role_ids: list[UUID] = Field(default_factory=list)


class UserStatusRequest(BaseModel):
    is_active: bool


class UserUpdateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    department: str | None = Field(default=None, max_length=128)

    @field_validator("username", "email")
    @classmethod
    def normalize_identity_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        if "@" not in value or any(character.isspace() for character in value):
            raise ValueError("Enter a valid email address.")
        return value.lower()

    @field_validator("department")
    @classmethod
    def normalize_department(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None


class UserPermissionsRequest(BaseModel):
    overrides: dict[str, bool]


class UserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=14, max_length=1024)


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=2000)
    permission_keys: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_role_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Role name must not be blank.")
        return normalized


class RoleUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_role_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Role name must not be blank.")
        return normalized


class RolePermissionsRequest(BaseModel):
    permission_keys: list[str]


class PermissionCreateRequest(BaseModel):
    key: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9][a-z0-9.-]+$")
    description: str = Field(min_length=1, max_length=2000)


class PermissionUpdateRequest(BaseModel):
    key: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9][a-z0-9.-]+$")
    description: str = Field(min_length=1, max_length=2000)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _is_locked(user: User, now: datetime) -> bool:
    locked_until = user.locked_until
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def _audit(
    request: Request,
    *,
    action: str,
    outcome: str,
    actor_user_id: UUID | None = None,
    resource_id: str | None = None,
    resource_type: str = "user_session",
    event_metadata: dict[str, object] | None = None,
) -> AuditLog:
    user_agent = request.headers.get("user-agent")
    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        source_ip=request.client.host if request.client else None,
        user_agent=user_agent[:1024] if user_agent else None,
        event_metadata=event_metadata or {},
    )
    attach_operation_event(
        audit_log,
        action=action,
        outcome=outcome,
        actor_user_id=actor_user_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )
    return audit_log


def _check_csrf(request: Request, auth_session: AuthSession) -> None:
    cookie_name = get_settings().csrf_cookie_name
    cookie_token = request.cookies.get(cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
        or not secrets.compare_digest(_digest(cookie_token), auth_session.csrf_token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_validation_failed")


def _validate_role_permissions(permission_keys: set[str]) -> None:
    conflict = separation_of_duties_conflict(permission_keys)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"separation_of_duties_conflict:{conflict}",
        )


def _is_superadmin(user: User) -> bool:
    return user.is_system_owner or any(role.name == "SuperAdmin" for role in user.roles)


def _effective_permission_keys(user: User) -> set[str]:
    permissions = {
        permission.permission_key
        for role in user.roles
        for permission in role.permissions
    }
    overrides = {
        override.permission.permission_key: override.is_granted
        for override in user.permission_overrides
    }
    permissions.update(key for key, is_granted in overrides.items() if is_granted)
    permissions.difference_update(key for key, is_granted in overrides.items() if not is_granted)
    return permissions


def _requires_mfa(user: User) -> bool:
    if _is_superadmin(user):
        return True
    return bool(
        _effective_permission_keys(user)
        & {"identity.users.manage", "identity.roles.manage"}
    )


def _mfa_cipher() -> Fernet:
    key = get_settings().mfa_encryption_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mfa_encryption_not_configured",
        )
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mfa_encryption_key_invalid",
        ) from error


def _decrypt_mfa_secret(encrypted_secret: bytes) -> str:
    try:
        return _mfa_cipher().decrypt(encrypted_secret).decode("ascii")
    except (InvalidToken, UnicodeDecodeError) as error:
        logger.exception("Unable to decrypt a stored TOTP secret")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mfa_secret_unavailable",
        ) from error


def _verify_totp(encrypted_secret: bytes, code: str) -> bool:
    secret = _decrypt_mfa_secret(encrypted_secret)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def _user_payload(user: User) -> dict[str, object]:
    roles = {role.name for role in user.roles}
    if user.is_system_owner:
        roles.add("SuperAdmin")
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "department": user.department,
        "facility_id": user.facility_id,
        "roles": sorted(roles),
        "is_system_owner": user.is_system_owner,
        "is_active": user.is_active,
        "mfa_enabled": user.totp_enabled_at is not None,
        "mfa_required": _requires_mfa(user),
        "permission_overrides": {
            override.permission.permission_key: override.is_granted
            for override in user.permission_overrides
        },
    }


async def get_auth_session(
    request: Request,
    db: DbSession,
) -> AuthSession:
    cookie_name = get_settings().session_cookie_name
    raw_token = request.cookies.get(cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required"
        )

    statement = (
        select(AuthSession)
        .options(
            selectinload(AuthSession.user).selectinload(User.roles).selectinload(Role.permissions),
            selectinload(AuthSession.user)
            .selectinload(User.permission_overrides)
            .selectinload(UserPermissionOverride.permission),
        )
        .where(
            AuthSession.token_hash == _digest(raw_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    auth_session = (await db.execute(statement)).scalar_one_or_none()
    if auth_session is None or not auth_session.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required"
        )
    return auth_session


def require_permission(permission_key: str):
    async def permission_guard(
        request: Request,
        db: DbSession,
        auth_session: Annotated[AuthSession, Depends(get_auth_session)],
    ) -> User:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            _check_csrf(request, auth_session)

        if _requires_mfa(auth_session.user) and auth_session.user.totp_enabled_at is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mfa_setup_required",
            )

        permissions = _effective_permission_keys(auth_session.user)
        if permission_key not in permissions and not _is_superadmin(auth_session.user):
            db.add(
                _audit(
                    request,
                    action=f"authorization.denied:{permission_key}",
                    outcome="denied",
                    actor_user_id=auth_session.user_id,
                )
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission_denied")
        return auth_session.user

    return permission_guard


def require_superadmin():
    async def superadmin_guard(
        request: Request,
        db: DbSession,
        auth_session: Annotated[AuthSession, Depends(get_auth_session)],
    ) -> User:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            _check_csrf(request, auth_session)
        if _requires_mfa(auth_session.user) and auth_session.user.totp_enabled_at is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mfa_setup_required",
            )
        if not _is_superadmin(auth_session.user):
            db.add(
                _audit(
                    request,
                    action="authorization.denied:superadmin",
                    outcome="denied",
                    actor_user_id=auth_session.user_id,
                )
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="superadmin_required")
        return auth_session.user

    return superadmin_guard


@router.post("/login")
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> dict[str, object]:
    settings = get_settings()
    statement = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .where(User.username == credentials.username)
        .with_for_update()
    )
    user = (await db.execute(statement)).scalar_one_or_none()
    now = datetime.now(UTC)

    if user is None:
        try:
            password_hasher.verify(dummy_password_hash, credentials.password)
        except VerifyMismatchError:
            pass
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="failure",
                resource_id=credentials.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if not user.is_active or _is_locked(user, now):
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="denied",
                actor_user_id=user.id,
                resource_id=user.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    try:
        password_valid = password_hasher.verify(user.password_hash, credentials.password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        password_valid = False

    if not password_valid:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_lockout_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            await db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == user.id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        db.add(
            _audit(
                request,
                action="authentication.login",
                outcome="failure",
                actor_user_id=user.id,
                resource_id=user.username,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if _requires_mfa(user) and user.totp_enabled_at is not None:
        if credentials.totp_code is None:
            db.add(
                _audit(
                    request,
                    action="authentication.mfa.challenge",
                    outcome="denied",
                    actor_user_id=user.id,
                    resource_id=user.username,
                )
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="mfa_code_required",
            )
        if (
            user.totp_secret_encrypted is None
            or not _verify_totp(user.totp_secret_encrypted, credentials.totp_code)
        ):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_lockout_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            db.add(
                _audit(
                    request,
                    action="authentication.mfa.verify",
                    outcome="failure",
                    actor_user_id=user.id,
                    resource_id=user.username,
                )
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_mfa_code",
            )

    user.failed_login_attempts = 0
    user.locked_until = None
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_digest(session_token),
            csrf_token_hash=_digest(csrf_token),
            expires_at=expires_at,
        )
    )
    db.add(
        _audit(
            request,
            action="authentication.login",
            outcome="success",
            actor_user_id=user.id,
            resource_id=user.username,
        )
    )
    await db.commit()

    secure_cookie = settings.environment.lower() != "development"
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=False,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    return {
        "user": {"id": str(user.id), "username": user.username},
        "csrf_token": csrf_token,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/me")
async def current_user(
    request: Request,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> dict[str, object]:
    user = auth_session.user
    permission_overrides = {
        override.permission.permission_key: override.is_granted
        for override in user.permission_overrides
    }
    permissions = _effective_permission_keys(user)
    if _is_superadmin(user):
        permissions.update((await db.scalars(select(Permission.permission_key))).all())
    db.add(
        _audit(
            request,
            action="identity.profile.read",
            outcome="success",
            actor_user_id=user.id,
            resource_id=str(user.id),
            resource_type="user",
        )
    )
    await db.commit()
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "department": user.department,
        "roles": sorted(
            {role.name for role in user.roles}
            | ({"SuperAdmin"} if user.is_system_owner else set())
        ),
        "is_system_owner": user.is_system_owner,
        "permissions": sorted(permissions),
        "permission_overrides": permission_overrides,
        "mfa_setup_required": _requires_mfa(user) and user.totp_enabled_at is None,
    }


@router.post("/mfa/setup")
async def start_mfa_setup(
    request: Request,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> dict[str, str]:
    user = auth_session.user
    _check_csrf(request, auth_session)
    if not _requires_mfa(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mfa_not_required")
    if user.totp_enabled_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="mfa_already_enabled")

    cipher = _mfa_cipher()
    if user.totp_pending_secret_encrypted is None:
        secret = pyotp.random_base32()
        user.totp_pending_secret_encrypted = cipher.encrypt(secret.encode("ascii"))
    else:
        try:
            secret = cipher.decrypt(user.totp_pending_secret_encrypted).decode("ascii")
        except (InvalidToken, UnicodeDecodeError) as error:
            logger.exception("Unable to decrypt a pending TOTP secret")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mfa_secret_unavailable",
            ) from error

    db.add(
        _audit(
            request,
            action="identity.mfa.enrollment.started",
            outcome="success",
            actor_user_id=user.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={"method": "totp"},
        )
    )
    await db.commit()
    return {
        "secret": secret,
        "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="TETHER",
        ),
    }


@router.post("/mfa/confirm")
async def confirm_mfa_setup(
    code_data: MfaCodeRequest,
    request: Request,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> dict[str, bool]:
    user = auth_session.user
    _check_csrf(request, auth_session)
    if not _requires_mfa(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mfa_not_required")
    if user.totp_enabled_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="mfa_already_enabled")
    if user.totp_pending_secret_encrypted is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="mfa_enrollment_not_started",
        )
    now = datetime.now(UTC)
    if _is_locked(user, now):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="account_temporarily_locked",
        )
    if not _verify_totp(user.totp_pending_secret_encrypted, code_data.code):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= get_settings().login_lockout_attempts:
            user.locked_until = now + timedelta(minutes=get_settings().login_lockout_minutes)
            await db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == user.id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        db.add(
            _audit(
                request,
                action="identity.mfa.enrollment.confirm",
                outcome="failure",
                actor_user_id=user.id,
                resource_id=str(user.id),
                resource_type="user",
                event_metadata={"method": "totp"},
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_mfa_code")

    user.totp_secret_encrypted = user.totp_pending_secret_encrypted
    user.totp_pending_secret_encrypted = None
    user.totp_enabled_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    db.add(
        _audit(
            request,
            action="identity.mfa.enrollment.confirm",
            outcome="success",
            actor_user_id=user.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={"method": "totp"},
        )
    )
    await db.commit()
    return {"mfa_enabled": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
) -> Response:
    _check_csrf(request, auth_session)
    auth_session.revoked_at = datetime.now(UTC)
    db.add(
        _audit(
            request,
            action="authentication.logout",
            outcome="success",
            actor_user_id=auth_session.user_id,
        )
    )
    await db.commit()
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", samesite="strict")
    response.delete_cookie(settings.csrf_cookie_name, path="/", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/users")
async def list_users(
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.read"))],
) -> list[dict[str, object]]:
    statement = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .order_by(User.username)
    )
    users = (await db.execute(statement)).scalars().unique().all()
    db.add(
        _audit(
            request,
            action="identity.users.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="user",
        )
    )
    await db.commit()
    return [_user_payload(user) for user in users]


async def _load_assignable_roles(
    db: AsyncSession,
    role_ids: list[UUID],
    *,
    allow_superadmin: bool = False,
) -> list[Role]:
    if len(set(role_ids)) != len(role_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="duplicate_role",
        )

    roles = (
        await db.execute(
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.id.in_(role_ids))
        )
    ).scalars().unique().all()
    if len(roles) != len(role_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unknown_role",
        )
    if not allow_superadmin and any(role.name == "SuperAdmin" for role in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_role_is_reserved",
        )
    return list(roles)


async def _active_superadmin_count(db: AsyncSession) -> int:
    active_superadmins = await db.scalars(
        select(User.id)
        .join(User.roles)
        .where(User.is_active.is_(True), Role.name == "SuperAdmin")
        .with_for_update()
    )
    return len(active_superadmins.all())


async def _protect_last_active_superadmin(
    db: AsyncSession,
    user: User,
    will_remain_superadmin: bool,
) -> None:
    if user.is_active and _is_superadmin(user) and not will_remain_superadmin:
        if await _active_superadmin_count(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot_remove_last_active_superadmin",
            )


async def _load_permission_records(
    db: AsyncSession,
    permission_keys: list[str],
) -> list[Permission]:
    if len(set(permission_keys)) != len(permission_keys):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="duplicate_permission",
        )
    if not permission_keys:
        return []

    permissions = (
        await db.execute(
            select(Permission).where(Permission.permission_key.in_(permission_keys))
        )
    ).scalars().all()
    if len(permissions) != len(permission_keys):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unknown_permission",
        )
    return list(permissions)


@router.get("/roles")
async def list_roles(
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.roles.read"))],
) -> list[dict[str, object]]:
    roles = (
        await db.execute(
            select(Role)
            .options(selectinload(Role.permissions))
            .order_by(Role.name)
        )
    ).scalars().unique().all()
    db.add(
        _audit(
            request,
            action="identity.roles.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="role",
        )
    )
    await db.commit()
    all_permission_keys = set(
        (await db.scalars(select(Permission.permission_key))).all()
    )
    return [
        {
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "permissions": sorted(
                all_permission_keys
                if role.name == "SuperAdmin"
                else (permission.permission_key for permission in role.permissions)
            ),
            "is_system": role.name == "SuperAdmin",
        }
        for role in roles
    ]


@router.get("/permissions")
async def list_permissions(
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.roles.read"))],
) -> list[dict[str, object]]:
    permissions = (
        await db.execute(select(Permission).order_by(Permission.permission_key))
    ).scalars().all()
    db.add(
        _audit(
            request,
            action="identity.permissions.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="permission",
        )
    )
    await db.commit()
    return [
        {
            "id": str(permission.id),
            "key": permission.permission_key,
            "description": permission.description,
            "is_system": permission.permission_key in permission_catalog(),
        }
        for permission in permissions
    ]


@router.post("/permissions", status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission_data: PermissionCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    existing_permission_id = await db.scalar(
        select(Permission.id).where(Permission.permission_key == permission_data.key)
    )
    if existing_permission_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="permission_already_exists",
        )
    permission = Permission(
        permission_key=permission_data.key,
        description=permission_data.description.strip(),
    )
    db.add(permission)
    await db.flush()
    db.add(
        _audit(
            request,
            action="identity.permission.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(permission.id),
            resource_type="permission",
            event_metadata={"key": permission.permission_key},
        )
    )
    await db.commit()
    return {
        "id": str(permission.id),
        "key": permission.permission_key,
        "description": permission.description,
        "is_system": False,
    }


@router.put("/permissions/{permission_id}")
async def update_permission(
    permission_id: UUID,
    permission_data: PermissionUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    permission = await db.get(Permission, permission_id)
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="permission_not_found",
        )
    previous_key = permission.permission_key
    builtin_keys = permission_catalog()
    if previous_key in builtin_keys and permission_data.key != previous_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="system_permission_key_is_reserved",
        )
    existing_permission_id = await db.scalar(
        select(Permission.id).where(
            Permission.permission_key == permission_data.key,
            Permission.id != permission.id,
        )
    )
    if existing_permission_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="permission_already_exists",
        )

    previous_description = permission.description
    permission.permission_key = permission_data.key
    permission.description = permission_data.description.strip()
    db.add(
        _audit(
            request,
            action="identity.permission.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(permission.id),
            resource_type="permission",
            event_metadata={
                "previous_key": previous_key,
                "key": permission.permission_key,
                "previous_description": previous_description,
                "description": permission.description,
            },
        )
    )
    await db.commit()
    return {
        "id": str(permission.id),
        "key": permission.permission_key,
        "description": permission.description,
        "is_system": previous_key in builtin_keys,
    }


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> Response:
    permission = await db.scalar(
        select(Permission)
        .options(
            selectinload(Permission.roles),
            selectinload(Permission.user_overrides),
        )
        .where(Permission.id == permission_id)
    )
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="permission_not_found",
        )
    if permission.permission_key in permission_catalog():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="system_permission_is_reserved",
        )
    if permission.roles or permission.user_overrides:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="permission_in_use",
        )

    key = permission.permission_key
    db.add(
        _audit(
            request,
            action="identity.permission.delete",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(permission.id),
            resource_type="permission",
            event_metadata={"key": key},
        )
    )
    await db.delete(permission)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-logs")
async def list_audit_logs(
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(
            require_permission(
                "quality-audit.read-only-audit-trail-and-transaction-reports.view"
            )
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    total = await db.scalar(select(func.count(AuditLog.id))) or 0
    entries = (
        await db.execute(
            select(AuditLog, User.username)
            .outerjoin(User, AuditLog.actor_user_id == User.id)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    db.add(
        _audit(
            request,
            action="quality-audit.audit-trail.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="audit_log",
            event_metadata={"limit": limit, "offset": offset},
        )
    )
    await db.commit()
    return {
        "items": [
            {
                "id": entry.id,
                "occurred_at": entry.occurred_at.isoformat(),
                "actor_username": actor_username,
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
                "outcome": entry.outcome,
            }
            for entry, actor_username in entries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    if role_data.name.casefold() == "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_role_is_reserved",
        )
    existing_role_id = await db.scalar(
        select(Role.id).where(func.lower(Role.name) == role_data.name.lower())
    )
    if existing_role_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_already_exists")

    permissions = await _load_permission_records(db, role_data.permission_keys)
    _validate_role_permissions({permission.permission_key for permission in permissions})
    role = Role(
        name=role_data.name,
        description=role_data.description.strip(),
        permissions=permissions,
    )
    db.add(role)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="role_already_exists",
        ) from error
    db.add(
        _audit(
            request,
            action="identity.role.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(role.id),
            resource_type="role",
            event_metadata={
                "name": role.name,
                "permissions": sorted(permission.permission_key for permission in permissions),
            },
        )
    )
    await db.commit()
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permission.permission_key for permission in permissions),
        "is_system": False,
    }


@router.put("/roles/{role_id}")
async def update_role(
    role_id: UUID,
    role_data: RoleUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    role = await db.scalar(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")
    if role.name == "SuperAdmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_role_is_reserved",
        )
    existing_role_id = await db.scalar(
        select(Role.id).where(
            func.lower(Role.name) == role_data.name.lower(),
            Role.id != role.id,
        )
    )
    if existing_role_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_already_exists")

    previous_name = role.name
    previous_description = role.description
    role.name = role_data.name
    role.description = role_data.description.strip()
    db.add(
        _audit(
            request,
            action="identity.role.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(role.id),
            resource_type="role",
            event_metadata={
                "previous_name": previous_name,
                "name": role.name,
                "previous_description": previous_description,
                "description": role.description,
            },
        )
    )
    await db.commit()
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permission.permission_key for permission in role.permissions),
        "is_system": False,
    }


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> Response:
    role = await db.scalar(
        select(Role).options(selectinload(Role.users)).where(Role.id == role_id)
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")
    if role.name == "SuperAdmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_role_is_reserved",
        )
    if role.users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_in_use")

    role_name = role.name
    db.add(
        _audit(
            request,
            action="identity.role.delete",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(role.id),
            resource_type="role",
            event_metadata={"name": role_name},
        )
    )
    await db.delete(role)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/roles/{role_id}/permissions")
async def replace_role_permissions(
    role_id: UUID,
    role_data: RolePermissionsRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    role = await db.scalar(
        select(Role)
        .options(
            selectinload(Role.permissions),
            selectinload(Role.users)
            .selectinload(User.roles)
            .selectinload(Role.permissions),
            selectinload(Role.users)
            .selectinload(User.permission_overrides)
            .selectinload(UserPermissionOverride.permission),
        )
        .where(Role.id == role_id)
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")
    if role.name == "SuperAdmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_role_is_reserved",
        )

    old_permissions = sorted(permission.permission_key for permission in role.permissions)
    permissions = await _load_permission_records(db, role_data.permission_keys)
    new_permission_keys = {
        permission.permission_key for permission in permissions
    }
    _validate_role_permissions(new_permission_keys)
    for user in role.users:
        assigned_permission_keys = new_permission_keys | {
            permission.permission_key
            for assigned_role in user.roles
            if assigned_role.id != role.id
            for permission in assigned_role.permissions
        }
        assigned_permission_keys.update(
            override.permission.permission_key
            for override in user.permission_overrides
            if override.is_granted
        )
        assigned_permission_keys.difference_update(
            override.permission.permission_key
            for override in user.permission_overrides
            if not override.is_granted
        )
        if not _is_superadmin(user):
            _validate_role_permissions(assigned_permission_keys)
    role.permissions = permissions
    new_permissions = sorted(permission.permission_key for permission in permissions)
    db.add(
        _audit(
            request,
            action="identity.role.permissions.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(role.id),
            resource_type="role",
            event_metadata={
                "name": role.name,
                "previous_permissions": old_permissions,
                "permissions": new_permissions,
            },
        )
    )
    await db.commit()
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "permissions": new_permissions,
        "is_system": False,
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.manage"))],
) -> dict[str, object]:
    existing_user_id = await db.scalar(
        select(User.id).where(
            (func.lower(User.username) == user_data.username.lower())
            | (func.lower(User.email) == user_data.email.lower())
        )
    )
    if existing_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user_already_exists")

    roles = await _load_assignable_roles(
        db,
        user_data.role_ids,
        allow_superadmin=_is_superadmin(current),
    )
    role_permission_keys = {
            permission.permission_key
            for role in roles
            for permission in role.permissions
    }
    if not any(role.name == "SuperAdmin" for role in roles):
        _validate_role_permissions(role_permission_keys)
    if _is_superadmin(current):
        facility_id = user_data.facility_id
        if facility_id is None and not any(role.name == "SuperAdmin" for role in roles):
            facility_id = 1
    else:
        facility_id = current.facility_id or 1
        if user_data.facility_id not in {None, facility_id}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="facility_access_denied",
            )
    if facility_id is not None:
        facility = await db.get(Facility, facility_id)
        if facility is None and facility_id == 1:
            facility = Facility(id=1, name="TETHER Development Facility", is_active=True)
            db.add(facility)
            await db.flush()
        if facility is None or not facility.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="active_facility_required",
            )
    user = User(
        username=user_data.username,
        email=user_data.email,
        department=user_data.department,
        facility_id=facility_id,
        password_hash=password_hasher.hash(user_data.password),
        roles=roles,
        permission_overrides=[],
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user_already_exists",
        ) from error
    db.add(
        _audit(
            request,
            action="identity.user.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={
                "username": user.username,
                "roles": sorted(role.name for role in roles),
            },
        )
    )
    await db.commit()
    return _user_payload(user)


@router.put("/users/{user_id}")
async def update_user(
    user_id: UUID,
    user_data: UserUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.manage"))],
) -> dict[str, object]:
    user = await db.scalar(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.is_system_owner and current.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_owner_account_is_reserved",
        )
    if _is_superadmin(user) and not _is_superadmin(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_account_is_reserved",
        )
    duplicate_user_id = await db.scalar(
        select(User.id).where(
            User.id != user.id,
            (func.lower(User.username) == user_data.username.lower())
            | (func.lower(User.email) == user_data.email.lower()),
        )
    )
    if duplicate_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user_already_exists")

    previous_values = {
        "username": user.username,
        "email": user.email,
        "department": user.department,
    }
    user.username = user_data.username
    user.email = user_data.email
    user.department = user_data.department
    db.add(
        _audit(
            request,
            action="identity.user.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={
                "previous": previous_values,
                "current": {
                    "username": user.username,
                    "email": user.email,
                    "department": user.department,
                },
            },
        )
    )
    await db.commit()
    return _user_payload(user)


@router.put("/users/{user_id}/roles")
async def replace_user_roles(
    user_id: UUID,
    user_data: UserRolesRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.manage"))],
) -> dict[str, object]:
    user = await db.scalar(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.id == current.id and not _is_superadmin(current):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot_change_own_roles")
    if user.is_system_owner and current.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_owner_account_is_reserved",
        )
    if _is_superadmin(user) and not _is_superadmin(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_account_is_reserved",
        )

    old_roles = sorted(role.name for role in user.roles)
    roles = await _load_assignable_roles(
        db,
        user_data.role_ids,
        allow_superadmin=_is_superadmin(current),
    )
    will_remain_superadmin = any(role.name == "SuperAdmin" for role in roles)
    if user.is_system_owner and not will_remain_superadmin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot_remove_system_owner_superadmin",
        )
    await _protect_last_active_superadmin(
        db,
        user,
        will_remain_superadmin,
    )
    effective_permissions = {
            permission.permission_key
            for role in roles
            for permission in role.permissions
    }
    effective_permissions.update(
        override.permission.permission_key
        for override in user.permission_overrides
        if override.is_granted
    )
    effective_permissions.difference_update(
        override.permission.permission_key
        for override in user.permission_overrides
        if not override.is_granted
    )
    if not any(role.name == "SuperAdmin" for role in roles):
        _validate_role_permissions(effective_permissions)
    user.roles = roles
    db.add(
        _audit(
            request,
            action="identity.user.roles.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={
                "username": user.username,
                "previous_roles": old_roles,
                "roles": sorted(role.name for role in roles),
            },
        )
    )
    await db.commit()
    return _user_payload(user)


@router.put("/users/{user_id}/permissions")
async def replace_user_permission_overrides(
    user_id: UUID,
    permissions_data: UserPermissionsRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> dict[str, object]:
    user = await db.scalar(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.is_system_owner:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="system_owner_permissions_are_immutable",
        )

    permissions = await _load_permission_records(db, list(permissions_data.overrides))
    permissions_by_key = {
        permission.permission_key: permission for permission in permissions
    }
    effective_permissions = {
        permission.permission_key
        for role in user.roles
        for permission in role.permissions
    }
    for key, is_granted in permissions_data.overrides.items():
        if is_granted:
            effective_permissions.add(key)
        else:
            effective_permissions.discard(key)
    if not _is_superadmin(user):
        _validate_role_permissions(effective_permissions)

    previous_overrides = {
        override.permission.permission_key: override.is_granted
        for override in user.permission_overrides
    }
    user.permission_overrides = [
        UserPermissionOverride(
            permission=permissions_by_key[key],
            is_granted=is_granted,
            updated_by=current.id,
            updated_at=datetime.now(UTC),
        )
        for key, is_granted in permissions_data.overrides.items()
    ]
    db.add(
        _audit(
            request,
            action="identity.user.permissions.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={
                "username": user.username,
                "previous_overrides": previous_overrides,
                "overrides": permissions_data.overrides,
            },
        )
    )
    await db.commit()
    return _user_payload(user)


@router.put("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: UUID,
    password_data: UserPasswordResetRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.manage"))],
) -> Response:
    user = await db.scalar(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.id == current.id and not _is_superadmin(current):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot_reset_own_password",
        )
    if user.is_system_owner and current.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_owner_account_is_reserved",
        )
    if _is_superadmin(user) and not _is_superadmin(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_account_is_reserved",
        )

    user.password_hash = password_hasher.hash(password_data.password)
    user.failed_login_attempts = 0
    user.locked_until = None
    revoked_at = datetime.now(UTC)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
    db.add(
        _audit(
            request,
            action="identity.user.password.reset",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={"username": user.username},
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/mfa/reset",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_user_mfa(
    user_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_superadmin())],
) -> Response:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.id == current.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot_reset_own_mfa")
    if user.is_system_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_owner_mfa_requires_trusted_host_recovery",
        )
    if user.totp_enabled_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="mfa_not_enabled")

    user.totp_secret_encrypted = None
    user.totp_pending_secret_encrypted = None
    user.totp_enabled_at = None
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.add(
        _audit(
            request,
            action="identity.mfa.reset",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={"username": user.username, "reset_by": current.username},
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: UUID,
    user_data: UserStatusRequest,
    request: Request,
    db: DbSession,
    current: Annotated[User, Depends(require_permission("identity.users.manage"))],
) -> dict[str, object]:
    user = await db.scalar(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(
                UserPermissionOverride.permission
            ),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.id == current.id and not _is_superadmin(current):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot_change_own_status")
    if user.is_system_owner and current.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_owner_account_is_reserved",
        )
    if user.is_system_owner and not user_data.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot_deactivate_system_owner",
        )
    if _is_superadmin(user) and not _is_superadmin(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superadmin_account_is_reserved",
        )

    previous_status = user.is_active
    if previous_status and not user_data.is_active:
        await _protect_last_active_superadmin(db, user, False)
    user.is_active = user_data.is_active
    if previous_status and not user.is_active:
        await db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    db.add(
        _audit(
            request,
            action="identity.user.status.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(user.id),
            resource_type="user",
            event_metadata={
                "username": user.username,
                "previous_is_active": previous_status,
                "is_active": user.is_active,
            },
        )
    )
    await db.commit()
    return _user_payload(user)
